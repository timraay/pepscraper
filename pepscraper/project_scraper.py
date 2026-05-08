import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence

from sqlmodel import SQLModel

from pepscraper.models import Project
from pepscraper.sql import save_models, set_sequence_start

SAVE_LOCK = asyncio.Lock()


class ProjectScraper(ABC):
    def __init__(self):
        self.project = self.get_project()

    @abstractmethod
    def get_project(self) -> Project: ...

    @abstractmethod
    async def get_proposals(self) -> Sequence[SQLModel]: ...

    @abstractmethod
    async def get_comments(self) -> Sequence[SQLModel]: ...

    async def run(self) -> None:
        project_name = self.project.project_name

        logging.info("%s: Starting project scraper", project_name)
        logging.info("%s: Fetching proposal revisions...", project_name)
        proposals = await self.get_proposals()
        logging.info("%s: Fetching proposal discussions...", project_name)
        comments = await self.get_comments()

        async with SAVE_LOCK:
            logging.info("%s: Acquiring save lock...", project_name)
            await set_sequence_start(self.get_sql_sequence_start())
            await save_models([self.project, *proposals, *comments])

        logging.info("%s: Saved all models!", project_name)

    def get_sql_sequence_start(self) -> int:
        return self.project.project_id * 1_000_000
