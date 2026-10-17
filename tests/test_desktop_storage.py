"""Portable initialization, path isolation and verified explicit upgrades."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from app.config import Settings, resolve_database_url
from app.desktop import bootstrap
from app.desktop.bootstrap import DesktopStorageError, prepare_desktop
from app.paths import persistent_root, portable_path, resource_root
from app.repositories.database import Database
from app.repositories.migrations import migration_config


def make_old_database(root: Path, revision="0003", *, initialized=True) -> Path:
    path = root / "data" / "memory.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.initialize()
    try:
        with database.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
            connection.execute(text("INSERT INTO sync_vault (id, token, initialized) VALUES (1, 'vault-token', :ready)"),
                               {"ready": int(initialized)})
    finally:
        database.dispose()
    if initialized:
        vault = root / "knowledge"
        (vault / "中文 子目录").mkdir(parents=True)
        (vault / ".memory-os-vault").write_text("vault-token", encoding="utf-8")
        (vault / "中文 子目录" / "保留.md").write_text("# 完整正文\n不修改。", encoding="utf-8")
        (vault / "空目录").mkdir()
    return path


def revision(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_first_start_uses_selected_root_independent_of_cwd(isolated_project, monkeypatch):
    root = isolated_project / "中文 便携版"
    root.mkdir()
    elsewhere = isolated_project / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    settings = prepare_desktop(root, lambda _: pytest.fail("Fresh DB must not ask upgrade permission"))
    database = Path(resolve_database_url(settings.database_url).database)
    assert database == root / "data" / "memory.db"
    assert revision(database) == "0004"
    assert settings.knowledge_path == root / "knowledge"
    assert settings.ai_config_path == root / "config" / "ai-providers.yml"
    assert not settings.ai_enabled and not settings.rag_enabled
    assert (root / "knowledge" / ".memory-os-vault").is_file()
    assert not (elsewhere / "data").exists()
    assert not (isolated_project / "data").exists()


def test_existing_templates_and_dotenv_are_never_overwritten(isolated_project):
    root = isolated_project
    (root / "config").mkdir()
    (root / "config" / "ai-providers.yml").write_text("private sentinel", encoding="utf-8")
    dotenv = "MEMORY_OS_LOG_LEVEL=WARNING\nMEMORY_OS_KNOWLEDGE_DIR=notes\n"
    (root / ".env").write_text(dotenv, encoding="utf-8")
    settings = prepare_desktop(root, lambda _: False)
    assert settings.log_level == "WARNING"
    assert settings.knowledge_path == root / "notes"
    assert (root / ".env").read_text(encoding="utf-8") == dotenv
    assert (root / "config" / "ai-providers.yml").read_text(encoding="utf-8") == "private sentinel"


def test_environment_still_overrides_portable_dotenv(isolated_project, monkeypatch):
    (isolated_project / ".env").write_text("MEMORY_OS_LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_OS_LOG_LEVEL", "DEBUG")
    assert prepare_desktop(isolated_project, lambda _: False).log_level == "DEBUG"


def test_current_portable_reopens_without_backup_or_migration(isolated_project, monkeypatch):
    first = prepare_desktop(isolated_project, lambda _: False)
    token = (first.knowledge_path / ".memory-os-vault").read_text()
    monkeypatch.setattr(bootstrap, "upgrade_database", lambda *_: pytest.fail("Already current"))
    second = prepare_desktop(isolated_project, lambda _: pytest.fail("Already current"))
    assert second.database_url == first.database_url
    assert (second.knowledge_path / ".memory-os-vault").read_text() == token
    assert not (isolated_project / "backups").exists()


@pytest.mark.parametrize("old_revision", ["0001", "0002", "0003"])
def test_old_revision_confirmed_upgrade_has_verified_full_backup(isolated_project, old_revision):
    database = make_old_database(isolated_project, old_revision)
    messages = []
    prepare_desktop(isolated_project, lambda message: messages.append(message) or True)
    assert messages and old_revision in messages[0]
    assert revision(database) == "0004"
    backup = next((isolated_project / "backups").iterdir())
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_revision"] == old_revision
    assert revision(backup / "memory.db") == old_revision
    assert (backup / "knowledge" / ".memory-os-vault").read_text() == "vault-token"
    assert (backup / "knowledge" / "空目录").is_dir()
    assert (backup / "knowledge" / "中文 子目录" / "保留.md").read_text(encoding="utf-8") == "# 完整正文\n不修改。"
    for entry in manifest["files"]:
        assert hashlib.sha256((backup / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_declining_upgrade_preserves_exact_database(isolated_project):
    database = make_old_database(isolated_project)
    before = database.read_bytes()
    with pytest.raises(DesktopStorageError, match="取消"):
        prepare_desktop(isolated_project, lambda _: False)
    assert database.read_bytes() == before
    assert not (isolated_project / "backups").exists()


def test_failed_backup_never_runs_migration(isolated_project, monkeypatch):
    database = make_old_database(isolated_project)
    before = database.read_bytes()
    monkeypatch.setattr(bootstrap, "backup_storage", lambda *_: (_ for _ in ()).throw(OSError("failure")))
    monkeypatch.setattr(bootstrap, "upgrade_database", lambda *_: pytest.fail("Backup failed"))
    with pytest.raises(DesktopStorageError):
        prepare_desktop(isolated_project, lambda _: True)
    assert database.read_bytes() == before


def test_backup_detects_directory_changes_before_migration(isolated_project, monkeypatch):
    from app.desktop import storage_backup
    database = make_old_database(isolated_project)
    before = database.read_bytes()
    original_copy = storage_backup.shutil.copy2

    def changing_copy(source, destination):
        result = original_copy(source, destination)
        (isolated_project / "knowledge" / "arrived-during-backup.md").write_text("external edit", encoding="utf-8")
        return result

    monkeypatch.setattr(storage_backup.shutil, "copy2", changing_copy)
    monkeypatch.setattr(bootstrap, "upgrade_database", lambda *_: pytest.fail("Backup was not stable"))
    with pytest.raises(DesktopStorageError):
        prepare_desktop(isolated_project, lambda _: True)
    assert database.read_bytes() == before


def test_unwritable_root_rejected_before_creating_templates(isolated_project, monkeypatch):
    def deny_write(*args, **kwargs):
        raise PermissionError("private-path-sentinel")

    monkeypatch.setattr(bootstrap.tempfile, "TemporaryFile", deny_write)
    with pytest.raises(DesktopStorageError) as error:
        prepare_desktop(isolated_project, lambda _: False)
    assert "private-path-sentinel" not in str(error.value)
    assert not (isolated_project / ".env").exists()
    assert not (isolated_project / "data").exists()


def test_failed_migration_keeps_preupgrade_backup(isolated_project, monkeypatch):
    from sqlalchemy.exc import OperationalError
    database = make_old_database(isolated_project)
    before = database.read_bytes()

    def fail_upgrade(*_):
        raise OperationalError("SQL private sentinel", {}, Exception("secret"))

    monkeypatch.setattr(bootstrap, "upgrade_database", fail_upgrade)
    with pytest.raises(DesktopStorageError) as error:
        prepare_desktop(isolated_project, lambda _: True)
    assert "secret" not in str(error.value)
    assert database.read_bytes() == before
    backup = next((isolated_project / "backups").iterdir())
    assert revision(backup / "memory.db") == "0003"


@pytest.mark.parametrize("change", ["missing_directory", "missing_marker", "wrong_marker"])
def test_initialized_vault_is_never_recreated_or_reidentified(isolated_project, change):
    database = make_old_database(isolated_project)
    marker = isolated_project / "knowledge" / ".memory-os-vault"
    if change == "missing_directory":
        (isolated_project / "knowledge").rename(isolated_project / "saved-knowledge")
    elif change == "missing_marker":
        marker.unlink()
    else:
        marker.write_text("unrelated", encoding="utf-8")
    before = database.read_bytes()
    with pytest.raises(DesktopStorageError, match="身份|缺失"):
        prepare_desktop(isolated_project, lambda _: pytest.fail("Invalid vault"))
    assert database.read_bytes() == before
    if change != "wrong_marker":
        assert not marker.exists()


@pytest.mark.parametrize("kind", ["corrupt", "unknown", "future", "missing_table"])
def test_unknown_and_corrupt_databases_rejected_without_rewrite(isolated_project, kind):
    database = isolated_project / "data" / "memory.db"
    database.parent.mkdir()
    if kind == "corrupt":
        database.write_bytes(b"not a sqlite database")
    elif kind == "unknown":
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE unrelated (x)")
    else:
        database = make_old_database(isolated_project)
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE alembic_version SET version_num = '9999'" if kind == "future"
                               else "DROP TABLE sync_states")
    before = database.read_bytes()
    with pytest.raises(DesktopStorageError):
        prepare_desktop(isolated_project, lambda _: pytest.fail("Invalid schema"))
    assert database.read_bytes() == before


@pytest.mark.parametrize("key,value", [
    ("MEMORY_OS_DATABASE_URL", "sqlite:///../outside.db"),
    ("MEMORY_OS_KNOWLEDGE_DIR", "../outside"),
    ("MEMORY_OS_AI_CONFIG_FILE", "../outside.yml"),
    ("MEMORY_OS_EMBEDDING_CONFIG_FILE", "../outside.yml"),
])
def test_external_portable_paths_rejected(isolated_project, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(DesktopStorageError):
        prepare_desktop(isolated_project, lambda _: False)
    assert not (isolated_project / "data").exists()


def test_portable_symlink_cannot_escape_root(isolated_project):
    outside = isolated_project.parent / "outside-desktop-state"
    outside.mkdir(exist_ok=True)
    link = isolated_project / "data"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symbolic link privilege not available")
    with pytest.raises(DesktopStorageError):
        prepare_desktop(isolated_project, lambda _: False)
    assert not (outside / "memory.db").exists()


def test_portable_runtime_root_does_not_change_resources_or_normal_settings(isolated_project):
    settings = Settings(runtime_root=isolated_project / "portable", _env_file=None)
    assert settings.knowledge_path == isolated_project / "portable" / "knowledge"
    assert "runtime_root" not in settings.model_dump()
    assert resource_root() != isolated_project
    assert migration_config().get_main_option("script_location") == str(resource_root() / "migrations")
    assert Settings(_env_file=None).runtime_root == isolated_project


def test_frozen_persistent_root_is_executable_parent_not_working_directory(isolated_project, monkeypatch):
    import sys
    executable = isolated_project / "portable" / "PersonalAiMemoryOs.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert persistent_root() == executable.parent


def test_initialization_refuses_nonempty_unidentified_vault(isolated_project):
    vault = isolated_project / "knowledge"
    vault.mkdir()
    (vault / "existing.md").write_text("Do not adopt", encoding="utf-8")
    with pytest.raises(DesktopStorageError, match="接管"):
        prepare_desktop(isolated_project, lambda _: False)
    assert not (isolated_project / "data" / "memory.db").exists()
