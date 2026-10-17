"""Isolated configuration and SQLite storage for every test."""

import os
from pathlib import Path
import tomllib

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import Settings
from app.main import create_app
from app.repositories.migrations import upgrade_database


@pytest.fixture(scope="session")
def project_version() -> str:
    manifest = Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["version"]


@pytest.fixture(autouse=True)
def isolated_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep environment values, dotenv files, and storage out of the real project."""
    for key in tuple(os.environ):
        if key.upper().startswith("MEMORY_OS_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setitem(Settings.model_config, "env_file", tmp_path / ".env")
    return tmp_path


@pytest.fixture
def sqlite_path(isolated_project: Path) -> Path:
    return isolated_project / "storage" / "memory.db"


@pytest.fixture
def sqlite_url(sqlite_path: Path) -> str:
    return f"sqlite:///{sqlite_path.as_posix()}"


@pytest.fixture
def migrated_database(sqlite_url: str) -> str:
    upgrade_database(sqlite_url)
    return sqlite_url


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(_env_file=None, database_url=migrated_database, sync_enabled=False)


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
