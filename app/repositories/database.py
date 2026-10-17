"""Synchronous SQLite connection lifecycle, independent of HTTP handlers."""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import resolve_database_url


class Database:
    """Own the engine for one application instance; create no business tables."""

    def __init__(self, database_url: str) -> None:
        self.url = resolve_database_url(database_url)
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None

    def initialize(self) -> None:
        """Prepare the storage directory and verify the SQLite connection."""
        database_path = Path(self.url.database)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            self.url,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _enable_foreign_keys)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.check_connection()

    def session(self) -> Session:
        """Give each request or background operation its own unit of work."""
        if self.session_factory is None:
            raise RuntimeError("Database has not been initialized.")
        return self.session_factory()

    def check_connection(self) -> None:
        """Check availability without modifying the database schema."""
        if self.engine is None:
            raise RuntimeError("Database has not been initialized.")
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        """Release pooled connections; safe even after a partial startup."""
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
        self.session_factory = None


def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
