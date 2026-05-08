import asyncio
import logging
import sys
from pathlib import Path

from pepscraper.models import Proposal
from pepscraper.project_scraper import ProjectScraper
from pepscraper.projects.pdep.main import PDEPProjectScraper
from pepscraper.projects.pep.main import PEPProjectScraper
from pepscraper.sql import create_tables, drop_tables, print_table_json

SCRAPERS: dict[str, ProjectScraper] = {
    "pdep": PDEPProjectScraper(),
    "pep": PEPProjectScraper(),
}

logging.basicConfig(
    format="[%(asctime)s][%(levelname)s] %(message)s",
    level=logging.INFO,
)


async def main() -> None:
    Path("data").mkdir(exist_ok=True)

    await drop_tables()
    await create_tables()

    project_names = sys.argv[1:]

    scrapers: list[ProjectScraper] = []
    if project_names:
        for project_name in project_names:
            if project_name not in SCRAPERS:
                logging.error(f"Unknown project: {project_name}")
            else:
                scrapers.append(SCRAPERS[project_name])
    else:
        scrapers = list(SCRAPERS.values())

    # Sort by project ID. Running scrapers out of order causes their autoincrementing
    # IDs to fall outside of their designated ranges.
    scrapers.sort(key=lambda s: s.project.project_id)

    for scraper in scrapers:
        await scraper.run()

    await print_table_json(Proposal)


if __name__ == "__main__":
    asyncio.run(main())
