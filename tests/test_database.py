"""Real SQLite connectivity, persistence, and connection cleanup."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from app.repositories.database import Database


def test_initialization_creates_storage_and_no_business_tables(
    sqlite_path: Path, sqlite_url: str
) -> None:
    database = Database(sqlite_url)
    assert database.engine is None
    assert not sqlite_path.parent.exists()

    try:
        database.initialize()
        database.check_connection()

        assert sqlite_path.is_file()
        assert database.engine is not None
        assert inspect(database.engine).get_table_names() == []
    finally:
        database.dispose()


def test_relative_url_uses_project_root_after_working_directory_changes(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working_directory = isolated_project / "elsewhere"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)
    database = Database("sqlite:///nested/memory.db")

    try:
        database.initialize()

        assert Path(database.url.database) == isolated_project / "nested" / "memory.db"
        assert (isolated_project / "nested" / "memory.db").is_file()
        assert not (working_directory / "nested").exists()
    finally:
        database.dispose()


def test_committed_data_survives_engine_recreation(sqlite_url: str) -> None:
    first_database = Database(sqlite_url)
    try:
        first_database.initialize()
        with first_database.engine.begin() as connection:
            connection.execute(text("CREATE TABLE persistence_probe (value TEXT)"))
            connection.execute(
                text("INSERT INTO persistence_probe (value) VALUES (:value)"),
                {"value": "persisted"},
            )
    finally:
        first_database.dispose()

    second_database = Database(sqlite_url)
    try:
        second_database.initialize()
        with second_database.engine.connect() as connection:
            assert connection.execute(
                text("SELECT value FROM persistence_probe")
            ).scalar_one() == "persisted"
    finally:
        second_database.dispose()


def test_dispose_releases_engine_and_is_idempotent(
    sqlite_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(sqlite_url)
    database.dispose()
    database.initialize()
    engine = database.engine
    dispose = Mock(wraps=engine.dispose)
    monkeypatch.setattr(engine, "dispose", dispose)

    database.dispose()
    database.dispose()

    dispose.assert_called_once_with()
    assert database.engine is None
    with pytest.raises(RuntimeError):
        database.check_connection()


def test_connection_check_requires_initialization(sqlite_url: str) -> None:
    with pytest.raises(RuntimeError):
        Database(sqlite_url).check_connection()


def test_storage_directory_failure_is_reported(
    isolated_project: Path,
) -> None:
    blocked_directory = isolated_project / "blocked"
    blocked_directory.write_text("A file cannot serve as a storage directory.", encoding="utf-8")
    database = Database(f"sqlite:///{(blocked_directory / 'memory.db').as_posix()}")

    try:
        with pytest.raises(OSError):
            database.initialize()
        assert database.engine is None
    finally:
        database.dispose()


def test_sqlite_connection_failure_is_reported_and_can_be_cleaned_up(
    sqlite_path: Path, sqlite_url: str
) -> None:
    sqlite_path.mkdir(parents=True)
    database = Database(sqlite_url)

    try:
        with pytest.raises(OperationalError):
            database.initialize()
    finally:
        database.dispose()

    assert database.engine is None
