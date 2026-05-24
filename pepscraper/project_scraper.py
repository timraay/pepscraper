import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import NamedTuple

from sqlmodel import SQLModel

from pepscraper.models import Person, Project
from pepscraper.sql import save_models, set_sequence_start

SAVE_LOCK = asyncio.Lock()


class PersonIdentify(NamedTuple):
    domain: str
    full_name: str | None = None
    email: str | None = None
    username: str | None = None


class ProjectScraper(ABC):
    def __init__(self):
        self.project = self.get_project()
        self._people: list[Person] = []

    def _get_person_by_full_name(self, full_name: str) -> Person | None:
        for person in self._people:
            if person.full_name == full_name:
                return person
        return None

    def _get_person_by_username(self, username: str, domain: str) -> Person | None:
        for person in self._people:
            for person_username in person.identifiers:
                if (
                    person_username.identifier == username
                    and person_username.domain == domain
                ):
                    return person
        return None

    def _get_person_by_identity(self, identity: PersonIdentify) -> Person | None:
        if identity.full_name is not None:
            person = self._get_person_by_full_name(identity.full_name)
            if person is not None:
                return person

        if identity.username is not None:
            person = self._get_person_by_username(identity.username, identity.domain)
            if person is not None:
                return person

        return None

    def get_person(self, identity: PersonIdentify) -> Person:
        person = self._get_person_by_identity(identity)
        if person is None:
            person = Person(full_name=identity.full_name)
            # Insert users with known full name at the beginning to prioritise them
            if person.full_name is None:
                self._people.append(person)
            else:
                self._people.insert(0, person)

        if identity.username is not None:
            person.add_identifier(identity.username, "username", identity.domain)

        if identity.email is not None:
            person.add_identifier(identity.email, "email", identity.domain)

        return person

    def get_people(self) -> Iterable[Person]:
        yield from self._people

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

        # TODO: Discard models not within START_DATE/END_DATE range.
        async with SAVE_LOCK:
            logging.info("%s: Acquiring save lock...", project_name)
            await set_sequence_start(self.get_sql_sequence_start())
            await save_models([self.project, *proposals, *comments])

        logging.info("%s: Saved all models!", project_name)

    def get_sql_sequence_start(self) -> int:
        return self.project.project_id * 1_000_000
