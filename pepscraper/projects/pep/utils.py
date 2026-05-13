import json
import logging
import re

from pepscraper.http import request_page
from pepscraper.project_scraper import PersonIdentify
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


def _get_author_match_to_name_and_email(
    match: re.Match[str],
    domain: str,
) -> PersonIdentify:
    name = match.group("name").strip().strip('"')
    email = match.group("email").strip().strip('"')
    return PersonIdentify(domain=domain, full_name=name, email=email)


def get_author_identity(author: str, domain: str) -> PersonIdentify:
    author = (
        author.replace(" at ", "@")
        .replace("[at]", "@")
        .replace(" dot ", ".")
        .replace("[dot]", ".")
    )

    email_name_match = RE_AUTHOR_EMAIL_FIRST.match(author)
    if email_name_match:
        return _get_author_match_to_name_and_email(email_name_match, domain=domain)

    name_first_match = RE_AUTHOR_NAME_FIRST.match(author)
    if name_first_match:
        return _get_author_match_to_name_and_email(name_first_match, domain=domain)

    if "@" in author:
        return PersonIdentify(domain=domain, full_name=None, email=author.strip())

    return PersonIdentify(domain=domain, full_name=author.strip(), email=None)


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

    author_identities: list[PersonIdentify] = []
    # TODO: Author might have "," in its name, for example "Fred L. Drake, Jr."
    for author in features["authors"].strip(" ,").split(","):
        author = author.strip()
        try:
            author_identity = get_author_identity(author, domain="peps.python.org")
            if author_identity in author_identities:
                logging.warning(
                    "Duplicate author name '%s': %s",
                    author_identity,
                    features["authors"],
                )
                continue
            author_identities.append(author_identity)
        except ValueError as e:
            logging.error("Skipping invalid author '%s': %s", author, e)

    # created_at = dateutil.parser.parse(features["created"])

    return PEPContentFeatures(
        title=features["title"].strip(),
        status=features["status"].strip().lower(),
        content=content.strip(),
        implemented_at_version=features.get("python_version"),
        author_identities=author_identities,
    )
