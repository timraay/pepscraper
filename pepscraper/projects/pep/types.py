from typing import Any, NamedTuple, TypedDict

from pepscraper.project_scraper import PersonIdentify


class PEPAPIResponseEntry(TypedDict):
    number: int
    title: str
    authors: str
    discussions_to: str | None
    status: str
    type: str
    topic: str
    created: str
    python_version: str | None
    post_history: str
    resolution: str | None
    requires: Any
    replaces: Any
    superseded_by: Any
    author_names: list[str]
    url: str


type PEPAPIResponse = dict[str, PEPAPIResponseEntry]


class GithubCommitAuthor(TypedDict):
    login: str
    displayName: str
    avatarUrl: str
    path: str
    profileName: str
    isGitHub: bool


class GithubCommit(TypedDict):
    oid: str
    url: str
    authoredDate: str
    committedDate: str
    shortMessage: str
    authors: list[GithubCommitAuthor]


class GithubCommitGroup(TypedDict):
    title: str
    commits: list[GithubCommit]


class GithubCommitDataPayload(TypedDict):
    commitGroups: list[GithubCommitGroup]


class GithubCommitDataPagination(TypedDict):
    startCursor: str
    endCursor: str
    hasNextPage: bool
    hasPreviousPage: bool


class GithubCommitDataFilters(TypedDict):
    since: str | None
    until: str | None
    author: str | None
    pagination: GithubCommitDataPagination


class GithubCommitData(TypedDict):
    payload: GithubCommitDataPayload
    filters: GithubCommitDataFilters


class GithubDeferredCommit(TypedDict):
    oid: str
    commentCount: int


class GithubDeferredCommitRenameHistory(TypedDict):
    historyUrl: str
    hasRenameCommits: bool
    oldName: str


class GithubDeferredCommitData(TypedDict):
    deferredCommits: list[GithubDeferredCommit]
    renameHistory: GithubDeferredCommitRenameHistory


class PEPContentFeatures(NamedTuple):
    title: str
    status: str
    # created_at: datetime
    content: str
    implemented_at_version: str | None
    author_identities: list[PersonIdentify]


class DiscourseTopicEntry(TypedDict):
    topic_id: int
    title: str


class DiscoursePostEntry(TypedDict, total=False):
    id: int
    post_number: int
    username: str
    name: str | None
    created_at: str
    reply_to_post_number: int | None
    raw: str | None
    cooked: str | None
