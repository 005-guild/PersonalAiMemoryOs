"""HTTP contract and application startup/shutdown behavior."""

import logging
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import Settings
from app.main import create_app


def test_application_creation_does_not_open_database(
    isolated_project: Path,
) -> None:
    sqlite_path = isolated_project / "not-created" / "memory.db"
    settings = Settings(_env_file=None, database_url=f"sqlite:///{sqlite_path.as_posix()}", sync_enabled=False)
    app = create_app(settings)

    assert app.state.settings is settings
    assert app.state.database.engine is None
    assert not sqlite_path.parent.exists()


def test_healthy_application_has_migrated_tables_and_releases_connections(
    settings: Settings,
) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
        assert {"sources", "knowledge", "sync_states", "alembic_version"}.issubset(
            inspect(app.state.database.engine).get_table_names()
        )

    assert app.state.database.engine is None


def test_openapi_and_documentation_are_available(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 200
        response = client.get("/openapi.json")

    assert response.status_code == 200
    health_schema = response.json()["paths"]["/health"]["get"]
    assert "200" in health_schema["responses"]
    assert "503" in health_schema["responses"]


def test_health_reports_runtime_database_failure_without_leaking_details(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)
    sensitive_message = "private-database-path-and-password-sentinel"

    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.database,
            "check_connection",
            Mock(side_effect=RuntimeError(sensitive_message)),
        )
        with caplog.at_level(logging.ERROR, logger="app"):
            response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert sensitive_message not in response.text
    assert sensitive_message not in caplog.text
    assert "Database health check failed" in caplog.text
    assert app.state.database.engine is None


def test_startup_failure_releases_partially_initialized_resources(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)
    database = app.state.database
    sensitive_message = "private-startup-configuration-sentinel"
    dispose = Mock(wraps=database.dispose)
    monkeypatch.setattr(database, "dispose", dispose)
    monkeypatch.setattr(
        database, "check_connection", Mock(side_effect=RuntimeError(sensitive_message))
    )

    with caplog.at_level(logging.ERROR, logger="app"):
        with pytest.raises(RuntimeError, match="Database startup failed") as error:
            with TestClient(app):
                pytest.fail("Application must not serve requests after failed startup.")

    dispose.assert_called_once_with()
    assert database.engine is None
    assert sensitive_message not in str(error.value)
    assert sensitive_message not in caplog.text
    assert "Database startup failed" in caplog.text


def test_invalid_environment_prevents_application_creation(
    monkeypatch: pytest.MonkeyPatch, isolated_project: Path
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("MEMORY_OS_DATABASE_URL", "sqlite:///:memory:")

    with pytest.raises(ValidationError):
        create_app()

    assert not (isolated_project / "data").exists()


def test_unmigrated_database_prevents_startup_without_creating_tables(
    isolated_project: Path,
) -> None:
    database_path = isolated_project / "unmigrated" / "memory.db"
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{database_path.as_posix()}", sync_enabled=False
    )
    app = create_app(settings)
    with pytest.raises(RuntimeError, match="Database startup failed"):
        with TestClient(app):
            pytest.fail("An unmigrated application must not start serving requests.")
    assert app.state.database.engine is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []
