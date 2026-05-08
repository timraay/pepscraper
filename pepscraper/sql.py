import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from pepscraper.constants import SQLITE_DB_URL

engine = create_async_engine(SQLITE_DB_URL)


def start_session():
    return AsyncSession(engine)


async def create_tables():
    logging.info("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_tables():
    logging.info("Dropping tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def save_models(models: list[SQLModel]):
    logging.info(f"Saving {len(models)} models...")
    async with start_session() as session:
        session.add_all(models)
        await session.commit()
    logging.info("Models saved!")


async def print_table_json(model: type[SQLModel]):
    async with start_session() as session:
        result = await session.execute(select(model))
        rows = result.scalars().all()
        for row in rows:
            print(row.model_dump_json())


async def fetch_tables_with_autoincrementing_ids() -> list[str]:
    # This is a bit hacky, but it works for SQLite. It may not work for other databases.
    # It assumes that all tables have an autoincrementing primary key named "id".
    # In a real application, you would want to be more robust than this.
    async with start_session() as session:
        result = await session.execute(
            text(
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND sql LIKE '%AUTOINCREMENT%'"
            )
        )
        return result.scalars().all()


async def set_sequence_start(start: int):
    seq = start - 1
    async with start_session() as session:
        # Get all table names with autoincrementing IDs
        table_names = await fetch_tables_with_autoincrementing_ids()

        # Replace sequence for each table by removing the old value and inserting new
        await session.execute(text("DELETE FROM sqlite_sequence"))
        for table_name in table_names:
            await session.execute(
                text("INSERT INTO sqlite_sequence(name, seq) VALUES (:name, :seq)"),
                {"name": table_name, "seq": seq},
            )
        await session.commit()
    logging.info(f"Set SQL sequence start to {start}")
