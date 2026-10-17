"""Configuration precedence, validation, and project-relative paths."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, resolve_database_url


def test_defaults_are_local_and_do_not_create_storage(isolated_project: Path) -> None:
    settings = Settings()

    assert settings.database_url == "sqlite:///data/memory.db"
    assert settings.log_level == "INFO"
    assert Path(resolve_database_url(settings.database_url).database) == (
        isolated_project / "data" / "memory.db"
    )
    assert not (isolated_project / "data").exists()


def test_project_dotenv_is_loaded_instead_of_working_directory_dotenv(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (isolated_project / ".env").write_text(
        "MEMORY_OS_DATABASE_URL=sqlite:///storage/from-project.db\n"
        "MEMORY_OS_LOG_LEVEL=WARNING\n",
        encoding="utf-8",
    )
    working_directory = isolated_project / "elsewhere"
    working_directory.mkdir()
    (working_directory / ".env").write_text(
        "MEMORY_OS_LOG_LEVEL=ERROR\n", encoding="utf-8"
    )
    monkeypatch.chdir(working_directory)

    settings = Settings()

    assert settings.database_url == "sqlite:///storage/from-project.db"
    assert settings.log_level == "WARNING"


def test_environment_overrides_dotenv(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (isolated_project / ".env").write_text(
        "MEMORY_OS_DATABASE_URL=sqlite:///storage/dotenv.db\n"
        "MEMORY_OS_LOG_LEVEL=WARNING\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORY_OS_DATABASE_URL", "sqlite:///storage/environment.db")
    monkeypatch.setenv("MEMORY_OS_LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.database_url == "sqlite:///storage/environment.db"
    assert settings.log_level == "DEBUG"


def test_explicit_configuration_overrides_environment(
    monkeypatch: pytest.MonkeyPatch, sqlite_url: str
) -> None:
    monkeypatch.setenv("MEMORY_OS_DATABASE_URL", "sqlite:///storage/environment.db")
    monkeypatch.setenv("MEMORY_OS_LOG_LEVEL", "ERROR")

    settings = Settings(database_url=sqlite_url, log_level="INFO")

    assert settings.database_url == sqlite_url
    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    "database_url",
    [
        "not-a-database-url",
        "postgresql://localhost/memory",
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///file:memory.db?uri=true",
        "sqlite:///memory.db?timeout=10",
        "sqlite://localhost/memory.db",
        "sqlite+aiosqlite:///memory.db",
    ],
)
def test_unsupported_database_configuration_is_rejected(database_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=database_url)


@pytest.mark.parametrize("field", ["database_url", "log_level"])
def test_validation_errors_do_not_display_sensitive_input(field: str) -> None:
    sensitive_value = "private-configuration-sentinel"
    value = (
        f"postgresql://user:{sensitive_value}@localhost/memory"
        if field == "database_url"
        else sensitive_value
    )

    with pytest.raises(ValidationError) as error:
        Settings(**{field: value})

    assert sensitive_value not in str(error.value)


def test_invalid_port_does_not_leak_url_input() -> None:
    sensitive_value = "private-port-sentinel"

    with pytest.raises(ValidationError) as error:
        Settings(database_url=f"sqlite://localhost:{sensitive_value}/memory.db")

    assert sensitive_value not in str(error.value)


@pytest.mark.parametrize("driver", ["sqlite", "sqlite+pysqlite"])
def test_relative_database_paths_resolve_from_project_root(
    driver: str, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working_directory = isolated_project / "working-directory"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)

    url = resolve_database_url(f"{driver}:///nested/memory.db")

    assert Path(url.database) == isolated_project / "nested" / "memory.db"
    assert not (working_directory / "nested").exists()


def test_absolute_database_path_is_preserved(sqlite_path: Path, sqlite_url: str) -> None:
    assert Path(resolve_database_url(sqlite_url).database) == sqlite_path
