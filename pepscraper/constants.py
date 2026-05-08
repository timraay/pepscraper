import os
from datetime import datetime, timedelta
from typing import Final

SQLITE_DB_URL: Final[str] = "sqlite+aiosqlite:///data/pepscraper.db"
GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")
GITHUB_HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {GITHUB_ACCESS_TOKEN}",
    "X-GitHub-Api-Version": "2026-03-10",
}

PYTHON_MAILING_LISTS: Final[tuple[tuple[str, timedelta], ...]] = (
    ("stdlib-sig", timedelta(days=365)),
    ("security-defenders-sig", timedelta(days=365)),
    ("linux-sig", timedelta(days=365)),
    ("overload-sig", timedelta(days=365)),
    ("cplusplus-sig", timedelta(days=90)),
    ("datetime-sig", timedelta(days=365)),
    ("db-sig", timedelta(days=365)),
    ("doc-sig", timedelta(days=365)),
    ("edu-sig", timedelta(days=365)),
    ("pythonmac-sig", timedelta(days=90)),
    ("security-sig", timedelta(days=365)),
    ("capi-sig", timedelta(days=365)),
    ("async-sig", timedelta(days=365)),
    ("typing-sig", timedelta(days=365)),
    ("distutils-sig", timedelta(days=90)),
    ("python-dev", timedelta(days=7)),
)
"""A list of Python mailing lists to scrape. The timedelta indicates the window size to
use. Large window sizes may cause API timeouts if the mailing list is very active."""

START_DATE: Final[datetime] = datetime(2000, 1, 1)
END_DATE: Final[datetime] = datetime(2026, 1, 1)

DEBUG: Final[bool] = True
