"""Alembic entry point using the same project-relative SQLite configuration."""

from alembic import context

from app.config import Settings, resolve_database_url
from app.models import Base
from app.repositories.database import Database


def migrate(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=resolve_database_url(Settings().database_url),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    provided_connection = context.config.attributes.get("connection")
    if provided_connection is not None:
        migrate(provided_connection)
    else:
        database = Database(Settings().database_url)
        try:
            database.initialize()
            with database.engine.begin() as connection:
                migrate(connection)
        finally:
            database.dispose()
