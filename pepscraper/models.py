from datetime import UTC, datetime
from typing import Annotated, Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, func
from sqlmodel import Field, Relationship, SQLModel


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
    comments: list["Comment"] = Relationship(back_populates="proposal")


class ProposalRevision(SQLModel, table=True):
    __tablename__ = "ProposalRevision"

    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    revision_index: Annotated[int, Field(primary_key=True)]
    title: str
    status: str
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
        # TODO: Re-enable
        # CheckConstraint(
        #     "status IN ('draft', 'active')", name="ck_proposal_revision_status"
        # ),
    )


class RelatedProposal(SQLModel, table=True):
    __tablename__ = "RelatedProposal"

    project_id: Annotated[int, Field(primary_key=True)]
    proposal_id: Annotated[str, Field(primary_key=True)]
    related_project_id: Annotated[int, Field(primary_key=True)]
    related_proposal_id: Annotated[str, Field(primary_key=True)]

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
        ForeignKeyConstraint(
            ["related_project_id", "related_proposal_id"],
            ["Proposal.project_id", "Proposal.proposal_id"],
        ),
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
