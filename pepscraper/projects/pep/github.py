import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from pepscraper.constants import GITHUB_HEADERS
from pepscraper.http import request_page
from pepscraper.projects.pep.types import (
    GithubCommit,
    GithubCommitData,
    GithubDeferredCommitData,
)


async def request_github_page(url: str, category: str) -> dict[str, Any]:
    return json.loads(
        await request_page(
            url,
            headers=GITHUB_HEADERS,
            category=category,
        )
    )


async def get_content_from_commit_data(
    project_name: str,
    repository: str,
    commit_data: GithubCommitData,
    index: int,
    file_name: str,
) -> AsyncGenerator[tuple[GithubCommit, str]]:
    for commit_group in commit_data["payload"]["commitGroups"]:
        for commit in commit_group["commits"]:
            content = await request_page(
                f"https://raw.githubusercontent.com/{repository}/{commit['oid']}/{file_name}",
                headers=GITHUB_HEADERS,
                category=f"{project_name.lower()}/{index:04d}",
            )

            page = 1
            while True:
                c = await request_github_page(
                    f"https://api.github.com/repos/{repository}/commits/{commit['oid']}?page={page}",
                    category=f"{project_name.lower()}/shared",
                )
                for file in c["files"]:
                    if file["filename"] == file_name:
                        if file["status"] == "renamed":
                            file_name = file["previous_filename"]
                        if file["status"] == "added":
                            yield commit, content
                            return

                if len(c["files"]) >= 300:
                    page += 1
                else:
                    break

            yield commit, content


async def get_commit_history_of_file(
    project_name: str, repository: str, index: int, file_name: str
) -> AsyncGenerator[tuple[GithubCommit, str]]:
    # file_name = f"peps/pep-{index:04d}.rst"
    commit_data = cast(
        GithubCommitData,
        await request_github_page(
            f"https://github.com/{repository}/commits/main/{file_name}",
            category=f"{project_name.lower()}/{index:04d}",
        ),
    )

    async for commit, content in get_content_from_commit_data(
        project_name, repository, commit_data, index, file_name
    ):
        yield commit, content

    deferred_commit_data = cast(
        GithubDeferredCommitData,
        await request_github_page(
            f"https://github.com/{repository}/commits/deferred_commit_data/main?original_branch=main&path={file_name}",
            category=f"{project_name.lower()}/{index:04d}",
        ),
    )
    rename_history = deferred_commit_data["renameHistory"]
    if not (rename_history and rename_history["hasRenameCommits"]):
        return

    # TODO: Pagination?
    file_name = deferred_commit_data["renameHistory"]["oldName"]
    rename_commit_data = cast(
        GithubCommitData,
        await request_github_page(
            "https://github.com" + deferred_commit_data["renameHistory"]["historyUrl"],
            category=f"{project_name.lower()}/{index:04d}",
        ),
    )

    async for commit, content in get_content_from_commit_data(
        project_name, repository, rename_commit_data, index, file_name
    ):
        yield commit, content
