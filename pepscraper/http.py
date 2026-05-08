import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Literal, TypedDict, overload

import aiofiles
import aiohttp

CACHED_PAGES_DIR = Path("./data/cached_pages")


class CachedPagesIndex:
    class Entry(TypedDict):
        name: str
        hash: str

    def __init__(self, category: str, index: dict[str, Entry]):
        self.category = category
        self.index = index
        self.path = CACHED_PAGES_DIR / Path(category)

        if not self.path.exists():
            self.path.mkdir(parents=True, exist_ok=True)

    @classmethod
    async def get(cls, category: str) -> "CachedPagesIndex":
        """Get a CachedPagesIndex instance, loading the index from disk if it exists."""
        self = cls(category, {})
        await self.reload()
        return self

    @staticmethod
    def hash_content(content: bytes) -> str:
        return hashlib.md5(content).hexdigest()

    @staticmethod
    def url_to_filename(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def has_entry(self, url: str) -> bool:
        """Check if the index has an entry for the given URL."""
        return url in self.index

    def get_entry(self, url: str) -> Entry | None:
        """Get the entry for the given URL, or None if it doesn't exist."""
        return self.index.get(url)

    async def _get_page(self, url: str) -> tuple[bytes, Path] | None:
        """Get the cached contents of the page and its path, or None if invalid."""
        # Get the entry
        entry = self.get_entry(url)
        if not entry:
            return None

        # Check if the file exists
        filepath = self.path / entry["name"]
        if not filepath.exists():
            return None

        # Read the content
        content = await self._read_page(filepath)

        # Check for valid hash
        is_valid = self.hash_content(content) == entry["hash"]
        if not is_valid:
            self.index.pop(url, None)
            await self.save()
            return None

        return content, filepath

    async def get_page(self, url: str) -> bytes | None:
        """Get the cached contents of the page, or None if it is invalid."""
        result = await self._get_page(url)
        if result is None:
            return None
        content, _ = result
        return content

    async def get_page_path(self, url: str) -> Path | None:
        """Get the path to the cached page, or None if it is invalid."""
        result = await self._get_page(url)
        if result is None:
            return None
        _, path = result
        return path

    async def _read_page(self, fp: Path) -> bytes:
        async with aiofiles.open(fp, mode="rb") as f:
            return await f.read()

    async def set_page(self, url: str, content: bytes) -> Path:
        filename = self.url_to_filename(url)
        filepath = self.path / filename

        # Write to disk
        await self._write_page(filepath, content)

        # Add to index
        content_hash = self.hash_content(content)
        self.index[url] = {"name": filename, "hash": content_hash}

        # Save the index
        await self.save()

        # Return the path to the cached page
        return filepath

    async def _write_page(self, fp: Path, content: bytes) -> None:
        async with aiofiles.open(fp, "wb") as f:
            await f.write(content)

    async def reload(self) -> None:
        fp = self.path / "index.json"
        if fp.exists():
            async with aiofiles.open(fp, encoding="utf-8") as f:
                self.index = json.loads(await f.read())

    async def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path / "index.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(self.index, indent=2))


PAGE_INDICES: dict[str, CachedPagesIndex] = {}


async def get_page_index(category: str) -> CachedPagesIndex:
    if category not in PAGE_INDICES:
        PAGE_INDICES[category] = await CachedPagesIndex.get(category)
    return PAGE_INDICES[category]


@overload
def optional_decode(content: bytes, encoding: str) -> str: ...


@overload
def optional_decode(content: bytes, encoding: Literal[None]) -> bytes: ...


def optional_decode(content: bytes, encoding: str | None) -> str | bytes:
    if encoding is not None:
        return content.decode(encoding, errors="replace")
    return content


async def download_page(url: str, headers: dict[str, str] | None = None) -> bytes:
    # Download the page
    logging.info("Downloading page: %s", url)
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.read()
        except aiohttp.ClientError as e:
            logging.error("Failed to download page: %s, error: %s", url, e)

            rl_remaining = response.headers.get("X-RateLimit-Remaining")
            if rl_remaining == "0":
                rl_reset = int(response.headers.get("X-RateLimit-Reset", 0))
                rl_current = time.time()
                sleep_time = max(0, rl_reset - rl_current) + 1
                logging.warning(
                    "Rate limit exceeded: %s. Retrying in %d seconds.",
                    url,
                    sleep_time,
                )
                await asyncio.sleep(sleep_time)

            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.read()


@overload
async def request_page(
    url: str,
    encoding: Literal[None],
    headers: dict[str, str] | None = None,
    category: str = "default",
) -> bytes: ...


@overload
async def request_page(
    url: str,
    encoding: str = "utf-8",
    headers: dict[str, str] | None = None,
    category: str = "default",
) -> str: ...


async def request_page(
    url: str,
    encoding: str | None = "utf-8",
    headers: dict[str, str] | None = None,
    category: str = "default",
) -> str | bytes:
    index = await get_page_index(category)

    # Return cached page if exists
    page = await index.get_page(url)
    if page is not None:
        return optional_decode(page, encoding)

    # Download the page
    content = await download_page(url, headers)

    # Add page to cache
    await index.set_page(url, content)

    return optional_decode(content, encoding)


async def request_page_path(
    url: str,
    headers: dict[str, str] | None = None,
    category: str = "default",
) -> Path:
    index = await get_page_index(category)

    # Return cached page if exists
    page_path = await index.get_page_path(url)
    if page_path is not None:
        return page_path

    # Download the page
    content = await download_page(url, headers)

    # Add page to cache
    page_path = await index.set_page(url, content)

    # Return the path to the cached page
    return page_path
