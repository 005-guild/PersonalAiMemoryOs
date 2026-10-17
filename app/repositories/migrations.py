"""Explicit schema upgrades; application startup only checks the revision."""

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

from app.models import Base
from app.paths import resource_root
from app.repositories.database import Database


def migration_config() -> Config:
    root = resource_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def upgrade_database(database_url: str) -> None:
    """Upgrade a specifically selected database without touching other files."""
    database = Database(database_url)
    try:
        database.initialize()
        with database.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        database.dispose()


def check_schema(engine: Engine) -> None:
    """Reject an uninitialized, outdated, or incomplete schema without modifying it."""
    expected_heads = set(ScriptDirectory.from_config(migration_config()).get_heads())
    with engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
        inspector = inspect(connection)
        actual_tables = set(inspector.get_table_names())
        complete = all(
            table.name in actual_tables
            and {column.name for column in table.columns}.issubset(
                {column["name"] for column in inspector.get_columns(table.name)}
            )
            for table in Base.metadata.sorted_tables
        )
    if current_heads != expected_heads or not complete:
        raise RuntimeError("Database schema is not current; run the explicit database upgrade.")


if __name__ == "__main__":
    import argparse

    from app.config import Settings

    parser = argparse.ArgumentParser(description="Upgrade the configured database schema.")
    parser.add_argument("--database-url", default=None)
    arguments = parser.parse_args()
    upgrade_database(arguments.database_url or Settings().database_url)
