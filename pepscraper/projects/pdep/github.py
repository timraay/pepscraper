import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

from pepscraper.projects.pep.github import request_github_page


def get_proposal_id_from_title(title: str) -> str:
    match = re.search(r"\bPDEP[-\s]?0*(\d+)\b", title, re.IGNORECASE)
    if match is None:
        raise ValueError(f"Could not determine PDEP number from title: {title}")
    return match.group(1)


async def get_pdep_pull_requests() -> list[dict[str, Any]]:
    pull_requests: list[dict[str, Any]] = []
    page = 1

    while True:
        query = urlencode(
            {
                "q": "repo:pandas-dev/pandas is:pr label:PDEP",
                "sort": "created",
                "order": "desc",
                "per_page": "100",
                "page": str(page),
            }
        )
        response = cast(
            dict[str, Any],
            await request_github_page(
                f"https://api.github.com/search/issues?{query}",
                category="pdep/shared",
            ),
        )
        items = cast(list[dict[str, Any]], response.get("items", []))
        if not items:
            break

        pull_requests.extend(
            item for item in items if item.get("pull_request") is not None
        )

        if len(items) < 100:
            break

        page += 1

    return pull_requests


async def get_pull_request_details(
    project_name: str, repository: str, pull_request_number: int
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await request_github_page(
            f"https://api.github.com/repos/{repository}/pulls/{pull_request_number}",
            category=f"{project_name.lower()}/pr{pull_request_number:04d}",
        ),
    )


async def get_pull_request_commits(
    project_name: str, repository: str, pull_request_number: int
) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    page = 1

    while True:
        response = cast(
            list[dict[str, Any]],
            await request_github_page(
                f"https://api.github.com/repos/{repository}/pulls/"
                f"{pull_request_number}/commits?per_page=100&page={page}",
                category=f"{project_name.lower()}/pr{pull_request_number:04d}",
            ),
        )
        if not response:
            break

        commits.extend(response)

        if len(response) < 100:
            break

        page += 1

    return commits


async def get_pull_request_files(
    project_name: str, repository: str, pull_request_number: int
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page = 1

    while True:
        response = cast(
            list[dict[str, Any]],
            await request_github_page(
                f"https://api.github.com/repos/{repository}/pulls/"
                f"{pull_request_number}/files?per_page=100&page={page}",
                category=f"{project_name.lower()}/pr{pull_request_number:04d}",
            ),
        )
        if not response:
            break

        files.extend(response)

        if len(response) < 100:
            break

        page += 1

    return files


async def get_pull_request_comments(
    project_name: str, repository: str, pull_request_number: int
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    page = 1

    while True:
        response = cast(
            list[dict[str, Any]],
            await request_github_page(
                f"https://api.github.com/repos/{repository}/issues/"
                f"{pull_request_number}/comments?per_page=100&page={page}",
                category=f"{project_name.lower()}/pr{pull_request_number:04d}",
            ),
        )
        if not response:
            break

        comments.extend(response)

        if len(response) < 100:
            break

        page += 1

    return comments


async def get_commit_files(
    project_name: str, repository: str, commit_sha: str
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page = 1

    while True:
        response = cast(
            dict[str, Any],
            await request_github_page(
                f"https://api.github.com/repos/{repository}/commits/{commit_sha}?page={page}",
                category=f"{project_name.lower()}/shared",
            ),
        )
        commit_files = cast(list[dict[str, Any]], response.get("files", []))
        if not commit_files:
            break

        files.extend(commit_files)

        if len(commit_files) < 300:
            break

        page += 1

    return files


def find_proposal_filename_in_pr(files: list[dict[str, Any]]) -> str:
    candidates = [
        file
        for file in files
        if file.get("status") != "removed" and "/pdeps/" in file["filename"].lower()
    ]
    if not candidates:
        raise ValueError("No proposal files found in pull request")

    def score(file: dict[str, Any]) -> tuple[int, int]:
        suffix = Path(str(file.get("filename", ""))).suffix.lower()
        is_text = int(suffix in {".md", ".rst", ".txt"})
        changes = int(file.get("additions", 0)) + int(file.get("deletions", 0))
        return is_text, changes

    return str(max(candidates, key=score)["filename"])
