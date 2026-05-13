import asyncio
import mailbox
import re
from collections.abc import Coroutine
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast

import aiofiles
from aiogzip import AsyncGzipBinaryFile

from pepscraper.constants import END_DATE, START_DATE
from pepscraper.http import request_page_path
from pepscraper.project_scraper import PersonIdentify
from pepscraper.projects.pep.utils import get_author_identity

MAILING_LIST_ARCHIVE_URL = "https://mail.python.org/archives/list/{list_name}@python.org/export/export.mbox.gz?start={from_.year}-{from_.month:02d}-{from_.day:02d}&end={to.year}-{to.month:02d}-{to.day:02d}"
MAILBOX_DIR = Path("data/mbox")

MAILING_LIST_START_DATE = max(START_DATE.date(), date(2000, 1, 1))
MAILING_LIST_END_DATE = min(END_DATE.date(), date(2024, 1, 1))
_MAILING_LIST_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(10)


async def download_mailing_list(list_name: str, from_: date, to: date) -> Path:
    # to += timedelta(days=1)
    url = MAILING_LIST_ARCHIVE_URL.format(list_name=list_name, from_=from_, to=to)
    gz_fp = await request_page_path(url, category="mail")

    mbox_fp = (
        MAILBOX_DIR / f"{list_name}_{from_.year}_{from_.month:02d}_{from_.day:02d}.mbox"
    )
    MAILBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Exit early if the unzipped mbox already exists (e.g. from a previous run)
    if mbox_fp.exists():
        return mbox_fp

    async with AsyncGzipBinaryFile(gz_fp) as gz, aiofiles.open(mbox_fp, "wb") as f:
        await f.write(await gz.read())

    return mbox_fp


def parse_mbox(mbox_path: Path) -> list[mailbox.mboxMessage]:
    mbox = mailbox.mbox(mbox_path)
    try:
        return list(mbox.values())
    finally:
        mbox.close()


async def _get_mailing_list_mails(
    list_name: str, date: date, time_delta: timedelta
) -> list[mailbox.mboxMessage]:
    async with _MAILING_LIST_DOWNLOAD_SEMAPHORE:
        mbox_path = await download_mailing_list(list_name, date, date + time_delta)
    return parse_mbox(mbox_path)


async def get_all_mailing_list_mails(
    list_name: str, time_delta: timedelta = timedelta(days=1)
) -> list[mailbox.mboxMessage]:
    messages = []

    date = MAILING_LIST_START_DATE

    coros: list[Coroutine[Any, Any, list[mailbox.mboxMessage]]] = []
    while date <= MAILING_LIST_END_DATE:
        coro = _get_mailing_list_mails(list_name, date, time_delta=time_delta)
        coros.append(coro)
        date += time_delta

    results = await asyncio.gather(*coros)
    messages = [message for result in results for message in result]
    return messages


RE_MAIL_SUBJECT = re.compile(r"^(?:Re:|\s+|\[.+?\])*([\w\W]+)$", re.IGNORECASE)
RE_MAIL_SUBJECT_PEP_NUMBER = re.compile(r"PEP[\s-]*(\d+)", re.IGNORECASE)


def get_mail_subject(mail: mailbox.mboxMessage) -> str:
    subject = decode_mime_words(mail.get("subject", ""))
    match = RE_MAIL_SUBJECT.match(subject)
    if match:
        return match.group(1).strip()
    return subject.strip()


def get_pep_number(subject: str) -> int | None:
    match = RE_MAIL_SUBJECT_PEP_NUMBER.search(subject)
    if match:
        return int(match.group(1))
    return None


def get_mail_pep_number(mail: mailbox.mboxMessage) -> int | None:
    subject = mail.get("subject", "")
    return get_pep_number(subject)


def get_mail_content(mail: mailbox.mboxMessage) -> str:
    content: str | None = None
    if mail.is_multipart():
        for part in mail.walk():
            if part.get_content_type() == "text/plain":
                content = cast(bytes, part.get_payload(decode=True)).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
                break
    else:
        content = cast(bytes, mail.get_payload(decode=True)).decode(
            mail.get_content_charset() or "utf-8", errors="replace"
        )

    return "" if content is None else decode_mime_words(content)


def get_mail_date(mail: mailbox.mboxMessage) -> datetime:
    date_str = mail.get("date")
    if date_str is None:
        raise ValueError("Mail is missing date header")

    # Try parsing the date using email.utils
    dt = parsedate_to_datetime(date_str)
    return dt


def get_mail_author(mail: mailbox.mboxMessage) -> PersonIdentify:
    author_str = mail.get("From")
    if author_str is None:
        raise ValueError("Mail is missing From header")

    return get_author_identity(decode_mime_words(author_str), domain="mail.python.org")


def decode_mime_words(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value
