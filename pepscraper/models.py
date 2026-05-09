from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    func,
)
from sqlmodel import Field, Relationship, SQLModel


def enum_to_check_constraint(
    enum_cls: type[StrEnum], column_name: str
) -> CheckConstraint:
    """# Do **not** use with untrusted inputs!!!"""
    return CheckConstraint(
        f"{column_name} IN ('" + "', '".join(enum_cls) + "')",
    )


class Project(SQLModel, table=True):
    __tablename__ = "Project"

    project_id: int = Field(primary_key=True)
    project_name: str
    enhancement_proposal_name: str
    copyright: str

    proposals: list["Proposal"] = Relationship(back_populates="project")


class Affiliation(SQLModel, table=True):
    __tablename__ = "Affiliation"

    organisation_id: Annotated[
        int | None,
        Field(
            foreign_key="Organisation.organisation_id",
            primary_key=True,
        ),
    ] = None
    person_id: Annotated[
        int | None, Field(foreign_key="Person.person_id", primary_key=True)
    ] = None


class ProposalRevisionAuthor(SQLModel, table=True):
    __tablename__ = "ProposalRevisionAuthor"

    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    revision_index: Annotated[int, Field(primary_key=True)]
    author_id: Annotated[int, Field(foreign_key="Person.person_id", primary_key=True)]

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id", "revision_index"],
            [
                "ProposalRevision.project_id",
                "ProposalRevision.proposal_id",
                "ProposalRevision.revision_index",
            ],
        ),
    )


class Person(SQLModel, table=True):
    __tablename__ = "Person"

    person_id: Annotated[int | None, Field(primary_key=True)] = None
    full_name: str

    usernames: list["PersonUsername"] = Relationship(back_populates="person")
    organizations: list["Organisation"] = Relationship(
        back_populates="people", link_model=Affiliation
    )
    proposals: list["Proposal"] = Relationship(back_populates="proposer")
    proposal_revisions: list["ProposalRevision"] = Relationship(
        back_populates="authors",
        link_model=ProposalRevisionAuthor,
    )
    comments: list["Comment"] = Relationship(back_populates="author")

    __table_args__ = ({"sqlite_autoincrement": True},)


class Organisation(SQLModel, table=True):
    __tablename__ = "Organisation"

    organisation_id: Annotated[int | None, Field(primary_key=True)] = None
    organisation_name: str

    people: list["Person"] = Relationship(
        back_populates="organizations", link_model=Affiliation
    )

    __table_args__ = ({"sqlite_autoincrement": True},)


class PersonUsername(SQLModel, table=True):
    __tablename__ = "PersonUsername"

    person_id: Annotated[
        int | None, Field(foreign_key="Person.person_id", primary_key=True)
    ] = None
    domain: Annotated[str, Field(primary_key=True)]
    username: Annotated[str, Field(primary_key=True)]
    real_name: str | None = None

    person: Person = Relationship(back_populates="usernames")


class Proposal(SQLModel, table=True):
    __tablename__ = "Proposal"

    project_id: Annotated[
        int, Field(foreign_key="Project.project_id", primary_key=True)
    ]
    proposal_id: Annotated[str, Field(primary_key=True)]
    proposer_id: Annotated[int, Field(foreign_key="Person.person_id")]
    topic: str | None
    proposal_type: str | None

    project: "Project" = Relationship(back_populates="proposals")
    proposer: "Person" = Relationship(back_populates="proposals")
    revisions: list["ProposalRevision"] = Relationship(back_populates="proposal")
    stage_history: list["StageHistory"] = Relationship(back_populates="proposal")
    comments: list["Comment"] = Relationship(back_populates="proposal")


class StageHistoryStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DRAFT = "draft"
    REVIEW = "review"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class StageHistory(SQLModel, table=True):
    __tablename__ = "StageHistory"
    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    stage_index: Annotated[int, Field(primary_key=True)]
    normalised_status: Annotated[
        StageHistoryStatus,
        Field(
            sa_column=Column(
                Enum(StageHistoryStatus, values_callable=lambda x: [i.value for i in x])
            )
        ),
    ]
    raw_status: str | None
    created_at: datetime

    proposal: "Proposal" = Relationship(back_populates="stage_history")

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
        enum_to_check_constraint(StageHistoryStatus, "normalised_status"),
    )

    @staticmethod
    def normalise_status(raw_status: str) -> StageHistoryStatus:
        raw_status = raw_status.lower().strip()
        return NORMALIZED_STATUS_MAP.get(raw_status, StageHistoryStatus.UNKNOWN)


NORMALIZED_STATUS_MAP: dict[str, StageHistoryStatus] = {
    "accepted": StageHistoryStatus.ACCEPTED,
    "stable": StageHistoryStatus.ACCEPTED,
    "approved": StageHistoryStatus.ACCEPTED,
    "implemented": StageHistoryStatus.ACCEPTED,
    "experimental": StageHistoryStatus.ACCEPTED,
    "published": StageHistoryStatus.ACCEPTED,
    "preview": StageHistoryStatus.ACCEPTED,
    "available": StageHistoryStatus.ACCEPTED,
    "final": StageHistoryStatus.ACCEPTED,
    "provisional": StageHistoryStatus.ACCEPTED,
    "rejected": StageHistoryStatus.REJECTED,
    "superseded": StageHistoryStatus.REJECTED,
    "replaced": StageHistoryStatus.REJECTED,
    "declined": StageHistoryStatus.REJECTED,
    "active": StageHistoryStatus.ACTIVE,
    "withdrawn": StageHistoryStatus.WITHDRAWN,
    "abandoned": StageHistoryStatus.WITHDRAWN,
    "deprecated": StageHistoryStatus.WITHDRAWN,
    "obsolete": StageHistoryStatus.WITHDRAWN,
    "review": StageHistoryStatus.REVIEW,
    "in review": StageHistoryStatus.REVIEW,
    "in progress": StageHistoryStatus.REVIEW,
    "in design": StageHistoryStatus.REVIEW,
    "discussion": StageHistoryStatus.REVIEW,
    "under discussion": StageHistoryStatus.REVIEW,
    "under discussions": StageHistoryStatus.REVIEW,
    "under consideration": StageHistoryStatus.REVIEW,
    "working on": StageHistoryStatus.REVIEW,
    "prototype": StageHistoryStatus.REVIEW,
    "posted": StageHistoryStatus.REVIEW,
    "submitted": StageHistoryStatus.REVIEW,
    "candidate": StageHistoryStatus.REVIEW,
    "funded": StageHistoryStatus.REVIEW,
    "draft": StageHistoryStatus.DRAFT,
    # "submitted": StageHistoryStatus.DRAFT,
    "deferred": StageHistoryStatus.DRAFT,
    "postponed": StageHistoryStatus.DRAFT,
    "proposed": StageHistoryStatus.DRAFT,
    "design": StageHistoryStatus.DRAFT,
    "incomplete": StageHistoryStatus.DRAFT,
    "complete": StageHistoryStatus.ACCEPTED,
    "finished": StageHistoryStatus.ACCEPTED,
}


class ProposalRevision(SQLModel, table=True):
    __tablename__ = "ProposalRevision"

    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    revision_index: Annotated[int, Field(primary_key=True)]
    title: str
    created_at: Annotated[
        datetime,
        Field(
            default_factory=datetime.now(tz=UTC),
            sa_column=Column(
                DateTime, nullable=False, server_default=func.current_timestamp()
            ),
        ),
    ]
    content: str | None
    implemented_at_version: str | None

    proposal: "Proposal" = Relationship(back_populates="revisions")
    authors: list["Person"] = Relationship(
        back_populates="proposal_revisions",
        link_model=ProposalRevisionAuthor,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
    )


class RelatedProposalType(StrEnum):
    RELATED = "related"
    SUPERSEDES = "supersedes"


class RelatedProposal(SQLModel, table=True):
    __tablename__ = "RelatedProposal"

    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    related_project_id: Annotated[int, Field(primary_key=True)]
    related_proposal_id: Annotated[str, Field(primary_key=True)]
    type: Annotated[
        RelatedProposalType,
        Field(
            sa_column=Column(
                Enum(
                    RelatedProposalType, values_callable=lambda x: [i.value for i in x]
                )
            )
        ),
    ]

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
        ForeignKeyConstraint(
            ["related_project_id", "related_proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
        enum_to_check_constraint(RelatedProposalType, "type"),
    )


class Comment(SQLModel, table=True):
    __tablename__ = "Comment"

    comment_id: Annotated[int | None, Field(primary_key=True)] = None
    author_id: Annotated[int | None, Field(foreign_key="Person.person_id")] = None
    project_id: int | None = None
    proposal_id: str | None = None
    comment_on_comment_id: Annotated[
        int | None, Field(foreign_key="Comment.comment_id")
    ] = None
    created_at: Annotated[
        datetime,
        Field(
            default_factory=datetime.now(tz=UTC),
            sa_column=Column(
                DateTime, nullable=False, server_default=func.current_timestamp()
            ),
        ),
    ]
    content: str

    proposal: Optional["Proposal"] = Relationship(back_populates="comments")
    author: Optional["Person"] = Relationship(back_populates="comments")
    parent: Optional["Comment"] = Relationship(
        back_populates="replies",
        sa_relationship_kwargs={"remote_side": "Comment.comment_id"},
    )
    replies: list["Comment"] = Relationship(back_populates="parent")

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
        {"sqlite_autoincrement": True},
    )
