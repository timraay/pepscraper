import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from aiohttp import ClientResponseError
from dateutil import parser
from sqlmodel import SQLModel

from pepscraper.constants import END_DATE
from pepscraper.http import request_page
from pepscraper.models import (
    Comment,
    Person,
    Project,
    Proposal,
    ProposalRevision,
    ProposalStatus,
)
from pepscraper.project_scraper import PersonIdentify, ProjectScraper
from pepscraper.projects.pdep.github import (
    find_proposal_filename_in_pr,
    get_commit_files,
    get_pdep_pull_requests,
    get_proposal_id_from_title,
    get_pull_request_comments,
    get_pull_request_commits,
    get_pull_request_details,
    get_pull_request_files,
)
from pepscraper.projects.pdep.utils import extract_features_from_content


class PDEPProjectScraper(ProjectScraper):
    def get_project(self) -> Project:
        return Project(
            project_id=1,
            project_name="Pandas",
            enhancement_proposal_name="PDEP",
            copyright="",  # TODO
        )

    async def _get_proposal_revision(
        self,
        pull_request_details: dict[str, Any],
        commit: dict[str, Any],
        proposal_filename: str,
    ) -> tuple[str, ProposalRevision, str] | None:
        created_at = parser.parse(str(commit["commit"]["author"]["date"]))
        if created_at > END_DATE:
            return None

        pull_request_number = int(pull_request_details["number"])
        try:
            proposal_id = get_proposal_id_from_title(str(pull_request_details["title"]))
        except ValueError as e:
            logging.error(str(e))
            return None

        commit_sha = str(commit["sha"])
        try:
            proposal_content = await request_page(
                "https://raw.githubusercontent.com/pandas-dev/pandas/"
                f"{commit_sha}/{proposal_filename}",
                category="pdep/shared",
            )
        except ClientResponseError as e:
            if e.status == 404:
                logging.warning(
                    "Failed to download proposal content for PDEP %s (PR #%s, commit"
                    " %s) since file %s did not exist in that commit",
                    proposal_id,
                    pull_request_number,
                    commit_sha[:8],
                    proposal_filename,
                )
            return None

        # Extract metadata from proposal content
        try:
            features = extract_features_from_content(str(proposal_content))
        except ValueError as e:
            logging.error(
                "Failed to extract features from PDEP %s: %s",
                proposal_id,
                e,
            )
            raise

        # Collect authors from proposal header
        authors: list[Person] = []
        for author_name in features.authors:
            author = self.get_person(author_name)
            authors.append(author)

        # If no authors in proposal, use commit author or PR author.
        if not authors:
            commit_author = cast(dict[str, Any] | None, commit.get("author"))
            if commit_author and commit_author.get("login"):
                proposer_name = str(commit_author["login"])
            else:
                commit_metadata = cast(dict[str, Any], commit.get("commit", {}))
                proposer_name = str(
                    cast(dict[str, Any], commit_metadata.get("author", {})).get(
                        "name", pull_request_details["user"]["login"]
                    )
                )
            proposer = self.get_person(
                PersonIdentify(domain="github.com", username=proposer_name)
            )
            authors = [proposer]

        proposal_revision = ProposalRevision(
            project_id=self.project.project_id,
            proposal_id=proposal_id,
            revision_index=0,
            title=features.title,
            # status=features.status.lower(),
            created_at=created_at,
            content=features.content,
            implemented_at_version=None,
            authors=authors,
        )

        status = features.status.lower()

        return proposal_id, proposal_revision, status

    async def get_proposals(self) -> Sequence[SQLModel]:
        proposals: dict[str, list[tuple[set[str], Proposal]]] = {}
        proposal_statuses: dict[str, list[tuple[datetime, str]]] = {}

        for pull_request in await get_pdep_pull_requests():
            pull_request_number = int(pull_request["number"])
            pull_request_details = await get_pull_request_details(
                "pdep", "pandas-dev/pandas", pull_request_number
            )

            files = await get_pull_request_files(
                "pdep", "pandas-dev/pandas", pull_request_number
            )
            try:
                proposal_filename = find_proposal_filename_in_pr(files)
            except ValueError:
                logging.warning(
                    "Pull request #%s (%s) does not modify any PDEP files",
                    pull_request_number,
                    pull_request["title"],
                )
                continue

            commits = await get_pull_request_commits(
                "pdep", "pandas-dev/pandas", pull_request_number
            )
            if not commits:
                continue

            current_filename = proposal_filename
            proposal_filenames: set[str] = {proposal_filename}
            proposal_revisions: list[ProposalRevision] = []
            statuses: list[tuple[datetime, str]] = []
            for commit in reversed(commits):
                # Fetch commit contents, extract proposal metadata, and create revision
                revision_data = await self._get_proposal_revision(
                    pull_request_details,
                    commit,
                    current_filename,
                )
                # Above step might return None if no revision could be extracted
                if not revision_data:
                    continue
                (proposal_id, proposal_revision, status) = revision_data

                # If the proposal file was renamed in this commit, use the previous
                # filename for the next commit.
                commit_files = await get_commit_files(
                    "pdep", "pandas-dev/pandas", str(commit["sha"])
                )
                for file in commit_files:
                    if (
                        file.get("status") == "renamed"
                        and file.get("filename") == current_filename
                        and file.get("previous_filename")
                    ):
                        current_filename = str(file["previous_filename"])
                        proposal_filenames.add(current_filename)
                        break

                # If content remains unchanged across revisions, the PDEP was unchanged
                # by this commit and we can skip it.
                if (
                    proposal_revisions
                    and proposal_revisions[-1].content == proposal_revision.content
                ):
                    logging.info(
                        "PDEP %s: Commit %s did not change proposal content, skipping",
                        proposal_id,
                        commit["sha"],
                    )
                    # Remove association with people, since backrefs could cause this
                    # model to be added to a session otherwise.
                    proposal_revision.authors = []
                    continue

                proposal_revisions.append(proposal_revision)
                statuses.append((proposal_revision.created_at, status))

            # If a proposal was created after END_DATE, no revisions will be extracted
            if not proposal_revisions:
                continue

            # Find an existing proposal.
            # PDEPs can take on the ID of previously rejected PDEPs, so we need to
            # check for matching filenames as well.
            proposal_id = proposal_revisions[-1].proposal_id
            existing_proposals = proposals.get(proposal_id, [])
            for existing_proposal_filenames, proposal in existing_proposals:  # noqa: B007
                if proposal_filenames.intersection(existing_proposal_filenames):
                    existing_proposal_filenames.update(proposal_filenames)
                    break
            else:
                # No existing proposal was found. Create a new proposal instead.
                proposal = Proposal(
                    project_id=self.project.project_id,
                    proposal_id=f"{proposal_id}-{len(existing_proposals) + 1}",
                    proposer_id=-1,
                    topic=None,
                    proposal_type=None,
                )
                proposals.setdefault(proposal_id, []).append(
                    (proposal_filenames, proposal)
                )

                # Proposer is the PR author
                proposer_name = str(pull_request_details["user"]["login"])
                proposer = self.get_person(
                    PersonIdentify(domain="github.com", username=proposer_name)
                )
                proposal.proposer = proposer

            # Append/assign revisions
            proposal.revisions.extend(proposal_revisions)
            proposal_statuses.setdefault(proposal.proposal_id, []).extend(statuses)

        # Sort revisions by creation date and assign revision indices
        for proposal_list in proposals.values():
            for _, proposal in proposal_list:
                proposal.revisions.sort(key=lambda revision: revision.created_at)

                for revision_index, revision in enumerate(proposal.revisions):
                    revision.revision_index = revision_index

                # Create proposal status history
                statuses = proposal_statuses[proposal.proposal_id]
                statuses.sort(key=lambda status: status[0])

                prev_status: str | None = None
                for created_at, status in statuses:
                    if status != prev_status:
                        proposal.statuses.append(
                            ProposalStatus(
                                project_id=self.project.project_id,
                                proposal_id=proposal.proposal_id,
                                status_index=len(proposal.statuses),
                                normalised_status=ProposalStatus.normalise_status(
                                    status
                                ),
                                raw_status=status,
                                created_at=created_at,
                            )
                        )
                        prev_status = status

        return [
            proposal
            for proposal_list in proposals.values()
            for _, proposal in proposal_list
        ]

    async def get_comments(self) -> Sequence[SQLModel]:
        models: list[Comment] = []

        for pull_request in await get_pdep_pull_requests():
            pull_request_created_at = parser.parse(pull_request["created_at"])
            if pull_request_created_at > END_DATE:
                continue

            pull_request_number = int(pull_request["number"])
            try:
                proposal_id = get_proposal_id_from_title(str(pull_request["title"]))
            except ValueError:
                logging.error(
                    "Could not determine PDEP number from PR title: %s",
                    pull_request["title"],
                )
                continue

            pull_request_details = await get_pull_request_details(
                "pdep", "pandas-dev/pandas", pull_request_number
            )

            pull_request_author_name = str(pull_request_details["user"]["login"])
            pull_request_author = self.get_person(
                PersonIdentify(domain="github.com", username=pull_request_author_name)
            )
            pull_request_comment = Comment(
                author_id=None,
                project_id=self.project.project_id,
                proposal_id=proposal_id,
                comment_on_comment_id=None,
                created_at=pull_request_created_at,
                content=str(pull_request_details.get("body", "")),
            )
            pull_request_comment.author = pull_request_author
            models.append(pull_request_comment)

            comments = await get_pull_request_comments(
                "pdep", "pandas-dev/pandas", pull_request_number
            )
            comments.sort(key=lambda comment: parser.parse(str(comment["created_at"])))
            for comment_data in comments:
                comment_created_at = parser.parse(comment_data["created_at"])
                if comment_created_at > END_DATE:
                    continue

                author_data = cast(dict[str, Any] | None, comment_data.get("user"))
                if not author_data or not author_data.get("login"):
                    continue

                author = self.get_person(
                    PersonIdentify(
                        domain="github.com", username=str(author_data["login"])
                    )
                )
                comment = Comment(
                    author_id=None,
                    project_id=self.project.project_id,
                    proposal_id=proposal_id,
                    comment_on_comment_id=None,
                    created_at=parser.parse(str(comment_data["created_at"])),
                    content=str(comment_data.get("body", "")),
                )
                comment.author = author
                comment.parent = models[-1]
                models.append(comment)

        return models
