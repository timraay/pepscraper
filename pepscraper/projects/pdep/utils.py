import re
from typing import NamedTuple, cast


class PDEPContentFeatures(NamedTuple):
    title: str
    status: str
    authors: list[str]
    created: str | None
    content: str


PDEP_HEADER_PATTERNS = [
    (re.compile(r"^#\s+PDEP-[\d#X]+:\s+(.+)$", re.MULTILINE), "title"),
    (re.compile(r"^-\s+Status:\s+(.+)$", re.MULTILINE), "status"),
    (
        re.compile(
            r"^-\s+Authors?:\s+(.+?)(?=\n-\s|\n\n|$)",
            re.MULTILINE | re.DOTALL,
        ),
        "authors",
    ),
    (re.compile(r"^-\s+Created:\s+(.+)$", re.MULTILINE), "created"),
]


def extract_features_from_content(content: str) -> PDEPContentFeatures:
    """Extract metadata and split header from PDEP content."""
    normalized_content = content.replace("\r\n", "\n")
    parts = re.split(r"\n(?=#+\s)", normalized_content, maxsplit=1)
    header = parts[0]
    body = parts[1] if len(parts) > 1 else ""

    features: dict[str, str | list[str]] = {}

    # Extract fields
    for pattern, field_name in PDEP_HEADER_PATTERNS:
        match = pattern.search(header)
        if match:
            value = match.group(1).strip()
            # For authors, split by comma or bracket links
            if field_name == "authors":
                # Extract author names, handling both "Name" and "[Name](url)" formats
                authors = []
                for author_text in re.split(r",\s*|\n\s*-\s+", value):
                    author_text = author_text.strip()
                    if not author_text:
                        continue
                    # Extract name from [Name](url) if present, otherwise use as-is
                    author_match = re.search(r"\[(.+?)\]", author_text)
                    if author_match:
                        authors.append(author_match.group(1))
                    else:
                        authors.append(author_text)
                features[field_name] = authors
            else:
                features[field_name] = value

    # Validate required fields
    if "title" not in features:
        raise ValueError("PDEP header is missing required field: title")
    if "status" not in features:
        raise ValueError("PDEP header is missing required field: status")

    return PDEPContentFeatures(
        title=cast(str, features.get("title", "")),
        status=cast(str, features.get("status", "")).lower(),
        authors=cast(list[str], features.get("authors", [])),
        created=cast(str | None, features.get("created")),
        content=body,
    )
