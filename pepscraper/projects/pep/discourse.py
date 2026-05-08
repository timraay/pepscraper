import json
import re

from pepscraper.http import request_page
from pepscraper.projects.pep.types import DiscoursePostEntry, DiscourseTopicEntry

DISCOURSE_TAG_URL = "https://discuss.python.org/c/peps/19.json"


async def get_tagged_topics() -> list[DiscourseTopicEntry]:
    topics: list[DiscourseTopicEntry] = []
    page = 0

    while True:
        page_data = await request_page(
            f"{DISCOURSE_TAG_URL}?page={page}",
            category=f"pep/discourse/tagged-topics/{page:04d}",
        )
        assert isinstance(page_data, str)
        data = json.loads(page_data)

        page_topics = data.get("topic_list", {}).get("topics", [])
        if not page_topics:
            break

        for topic in page_topics:
            topics.append(
                {
                    "topic_id": int(topic["id"]),
                    "title": str(topic["title"]),
                }
            )

        if len(page_topics) == 0:
            break
        page += 1

    unique: dict[int, DiscourseTopicEntry] = {}
    for t in topics:
        unique[t["topic_id"]] = t

    return list(unique.values())


async def get_topic_posts(topic_id: int) -> list[DiscoursePostEntry]:
    topic_data = await request_page(
        f"https://discuss.python.org/t/{topic_id}.json?include_raw=1",
        category=f"pep/discourse/{topic_id:06d}",
    )
    assert isinstance(topic_data, str)
    data = json.loads(topic_data)
    return list(data["post_stream"]["posts"])


def get_pep_number_from_title(title: str) -> int | None:
    match = re.search(r"\bPEP[\s-]*(\d+)\b", title, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))
