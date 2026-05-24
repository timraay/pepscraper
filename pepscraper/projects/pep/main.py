import asyncio
import itertools
import logging
import mailbox

import dateutil
from sqlmodel import SQLModel

from pepscraper.constants import PYTHON_MAILING_LISTS
from pepscraper.models import (
    Comment,
    Project,
    Proposal,
    ProposalRevision,
    ProposalStatus,
)
from pepscraper.project_scraper import PersonIdentify, ProjectScraper
from pepscraper.projects.pep.discourse import (
    get_pep_number_from_title,
    get_tagged_topics,
    get_topic_posts,
)
from pepscraper.projects.pep.github import get_commit_history_of_file
from pepscraper.projects.pep.mails import (
    get_all_mailing_list_mails,
    get_mail_author,
    get_mail_content,
    get_mail_date,
    get_mail_subject,
    get_pep_number,
)
from pepscraper.projects.pep.types import PEPAPIResponseEntry
from pepscraper.projects.pep.utils import (
    extract_features_from_content,
    get_pep_list,
)


class PEPProjectScraper(ProjectScraper):
    def get_project(self) -> Project:
        return Project(
            project_id=0,
            project_name="Python",
            enhancement_proposal_name="PEP",
            copyright="",  # TODO
        )

    async def _get_proposal_revisions(
        self, project: Project, pep: PEPAPIResponseEntry
    ) -> list[SQLModel]:
        # Create proposal
        proposal = Proposal(
            project_id=project.project_id,
            proposal_id=str(pep["number"]),
            proposer_id=-1,
            topic=pep["topic"],
            proposal_type=pep["type"],
            revisions=[],
            stage_history=[],
        )

        # Fetch revisions
        pep_number = pep["number"]
        history = [
            c
            async for c in get_commit_history_of_file(
                "pep", "python/peps", pep_number, f"peps/pep-{pep_number:04d}.rst"
            )
        ]
        # Sort by oldest first
        history.sort(key=lambda c: dateutil.parser.parse(c[0]["committedDate"]))

        old_content: str | None = None
        revision_index = -1
        for commit, content in history:
            # If content remains unchanged across revisions, the PDEP was unchanged
            # by this commit and we can skip it.
            if old_content == content:
                logging.debug(
                    "PEP %s: Commit %s did not change proposal content, skipping",
                    proposal.proposal_id,
                    commit["oid"],
                )
                continue

            try:
                features = extract_features_from_content(content)
            except ValueError as e:
                logging.error(
                    "Failed to extract features from PEP %s (rev. %s): %s",
                    pep["number"],
                    revision_index + 1,
                    e,
                )
                continue

            revision_index += 1
            old_content = content
            created_at = dateutil.parser.parse(commit["committedDate"])

            # Create revision
            proposal_revision = ProposalRevision(
                project_id=project.project_id,
                proposal_id=str(pep["number"]),
                revision_index=revision_index,
                title=features[0],
                # status=features[1],
                created_at=created_at,
                content=features[2],
                implemented_at_version=features[3],
            )
            for author_name in features[4]:
                author = self.get_person(author_name)
                proposal_revision.authors.append(author)

            proposal.revisions.append(proposal_revision)

            # Update stage history
            if (
                len(proposal.stage_history) == 0
                or proposal.stage_history[-1].raw_status != features[1]
            ):
                proposal.stage_history.append(
                    ProposalStatus(
                        project_id=project.project_id,
                        proposal_id=str(pep["number"]),
                        stage_index=len(proposal.stage_history),
                        normalised_status=ProposalStatus.normalise_status(features[1]),
                        raw_status=features[1],
                        created_at=created_at,
                    )
                )

        proposal.proposer = proposal_revision.authors[-1]

        return [proposal]

    async def get_proposals(self) -> list[SQLModel]:
        models: list[SQLModel] = []

        # Get a list of PEPs
        pep_list = await get_pep_list()

        # For each PEP, get all revisions
        for batch in itertools.batched(pep_list.values(), 10, strict=False):
            results = await asyncio.gather(
                *[
                    self._get_proposal_revisions(self.project, pep)
                    for pep in batch
                    if pep["number"] > 0
                ]
            )
            for result in results:
                models.extend(result)

        return models

    async def get_comments(self) -> list[SQLModel]:
        models: list[SQLModel] = [
            *(await self._get_comments_from_mails()),
            *(await self._get_comments_from_discourse()),
        ]
        return models

    async def _get_comments_from_mails(self) -> list[SQLModel]:
        models: list[SQLModel] = []

        # Receive all mails
        mail_by_subject: dict[str, list[mailbox.mboxMessage]] = {}
        for list_name, time_delta in PYTHON_MAILING_LISTS:
            logging.info("Receiving mailing list: %s", list_name)
            mails = await get_all_mailing_list_mails(list_name, time_delta=time_delta)
            for mail in mails:
                # Group mails by subject
                subject = get_mail_subject(mail)
                mail_by_subject.setdefault(subject, []).append(mail)
            logging.info("Received %s mails from %s", len(mails), list_name)

        # Categorize mails by PEP number and sort by date
        logging.info(
            "Sorting %s total mails",
            sum(len(mails) for mails in mail_by_subject.values()),
        )
        for subject, mails in mail_by_subject.items():
            # Search for PEP reference in the subject
            pep_number = get_pep_number(subject)
            if pep_number is None:
                continue

            # Sort mails by date
            mails.sort(key=get_mail_date)

            # Create Comment models
            prev_comment: Comment | None = None
            for mail in mails:
                author = self.get_person(get_mail_author(mail))
                message = Comment(
                    author_id=None,
                    project_id=self.project.project_id,
                    proposal_id=str(pep_number),
                    comment_on_comment_id=None,
                    created_at=get_mail_date(mail),
                    content=get_mail_content(mail),
                )
                message.parent = prev_comment
                message.author = author
                prev_comment = message
                models.append(message)

        return models

    async def _get_comments_from_discourse(self) -> list[SQLModel]:
        models: list[SQLModel] = []

        for topic in await get_tagged_topics():
            title = str(topic["title"])
            pep_number = get_pep_number_from_title(title)
            if pep_number is None:
                logging.warning(
                    "Skipping Discourse topic without a PEP number in the title: %s",
                    title,
                )
                continue

            posts = await get_topic_posts(topic["topic_id"])
            comments_by_post_number: dict[int, Comment] = {}

            previous_comment: Comment | None = None
            for post in sorted(posts, key=lambda post: int(post["post_number"])):
                author = self.get_person(
                    PersonIdentify(
                        domain="discuss.python.org",
                        full_name=post.get("name"),
                        username=post.get("username"),
                    )
                )
                content = str(post.get("raw") or post.get("cooked") or "")
                # TODO: Will this cause issues if no Proposal exists with this ID?
                comment = Comment(
                    author_id=None,
                    project_id=self.project.project_id,
                    proposal_id=str(pep_number),
                    comment_on_comment_id=None,
                    created_at=dateutil.parser.isoparse(str(post["created_at"])),
                    content=content,
                )
                comment.author = author

                reply_to_post_number = post.get("reply_to_post_number")
                if reply_to_post_number is not None:
                    comment.parent = comments_by_post_number.get(
                        int(reply_to_post_number)
                    )
                else:
                    comment.parent = previous_comment

                previous_comment = comment
                comments_by_post_number[int(post["post_number"])] = comment
                models.append(comment)

        return models
