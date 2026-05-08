import json
import logging
import re

from pepscraper.http import request_page
from pepscraper.projects.pep.types import (
    PEPAPIResponse,
    PEPContentFeatures,
)

PEP_API_URL = "https://peps.python.org/api/peps.json"


async def get_pep_list() -> PEPAPIResponse:
    return json.loads(await request_page(PEP_API_URL, category="pep"))


RE_AUTHOR_EMAIL_FIRST = re.compile(
    r"^(?P<email>[^\s]*?@[^\s]+?)\s*[(<](?P<name>.*?)[)>]?\s*$"
)
RE_AUTHOR_NAME_FIRST = re.compile(
    r"^(?P<name>.*?)\s*[(<](?P<email>[^\s]*?@[^\s]+?)[)>]?\s*$"
)


def get_author_full_name(author: str) -> str:
    author = (
        author.replace(" at ", "@")
        .replace("[at]", "@")
        .replace(" dot ", ".")
        .replace("[dot]", ".")
    )

    email_name_match = RE_AUTHOR_EMAIL_FIRST.match(author)
    if email_name_match:
        return email_name_match.group("name").strip().strip('"')

    name_first_match = RE_AUTHOR_NAME_FIRST.match(author)
    if name_first_match:
        return name_first_match.group("name").strip().strip('"')

    # if "@" in author or " " not in author:
    #     raise ValueError(f"Invalid author: {author}")

    return author


PEP_HEADER_FEATURES: list[tuple[re.Pattern, bool]] = [
    # (re.compile(r"^PEP:[ \t]+(?P<index>\d+)$", re.MULTILINE), True),
    (re.compile(r"^Title:[ \t]+(?P<title>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Version:[ \t]+(?P<version>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Revision:[ \t]+(?P<revision>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Last-Modified:[ \t]+(?P<last_modified>.+)$", re.MULTILINE), True),
    (
        re.compile(
            r"^(?:Author|Owner)s?:[ \t]+(?P<authors>(?:,\n\s+|.)+)$", re.MULTILINE
        ),
        True,
    ),
    # (re.compile(r"^Discussions-To: +(?P<discussion_to>.+)$", re.MULTILINE), False),
    (re.compile(r"^Status:[ \t]+(?P<status>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Type:[ \t]+(?P<type>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Content-Type:[ \t]+(?P<content_type>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Requires:[ \t]+(?P<requires>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Topic:[ \t]+(?P<topic>.+)$", re.MULTILINE), True),
    # (re.compile(r"^Created:[ \t]+(?P<created>.+)$", re.MULTILINE), True),
    (re.compile(r"^Python-Version:[ \t]+(?P<python_version>.+)$", re.MULTILINE), False),
    # (re.compile(r"^Post-History: +(?P<post_history>[\w\W]*?)$", re.MULTILINE), True),
]


def extract_features_from_content(content: str) -> PEPContentFeatures:
    header, content = re.split(r"\n{2,}", content.replace("\r\n", "\n"), maxsplit=1)

    features: dict[str, str] = {}
    for re_feature, is_required in PEP_HEADER_FEATURES:
        match = re_feature.search(header)
        if not match:
            if not is_required:
                continue

            raise ValueError(
                f"PEP header is missing required feature: {re_feature.pattern}"
            )

        features.update(match.groupdict())

    # TODO: Use post-history to determine significant revisions

    author_names: list[str] = []
    # TODO: Author might have "," in its name, for example "Fred L. Drake, Jr."
    for author in features["authors"].strip(" ,").split(","):
        author = author.strip()
        try:
            author_name = get_author_full_name(author)
            if author_name in author_names:
                logging.warning(
                    "Duplicate author name '%s': %s", author_name, features["authors"]
                )
                continue
            author_names.append(author_name)
        except ValueError as e:
            logging.error("Skipping invalid author '%s': %s", author, e)

    # created_at = dateutil.parser.parse(features["created"])

    return PEPContentFeatures(
        title=features["title"].strip(),
        status=features["status"].strip().lower(),
        content=content.strip(),
        implemented_at_version=features.get("python_version"),
        author_names=author_names,
    )
