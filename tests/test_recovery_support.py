import json
from pathlib import Path

import pytest

from app.desktop.bootstrap import _initialize_vault
from app.desktop.storage_backup import backup_storage
from app.repositories.migrations import upgrade_database
from scripts.recovery_support import backup_configuration, restore_new, verify_backup


@pytest.fixture
def backup(tmp_path):
    root = tmp_path / "source"
    database = root / "data/memory.db"
    database.parent.mkdir(parents=True)
    upgrade_database(f"sqlite:///{database.as_posix()}")
    _initialize_vault(database, root / "knowledge")
    (root / "knowledge/中文 空格.md").write_text("完整正文\n```python\nprint(1)\n```", encoding="utf-8")
    (root / "knowledge/empty").mkdir()
    (root / "config").mkdir()
    (root / "config/ai-providers.yml").write_text("schema_version: 1\nprofiles: {}", encoding="utf-8")
    (root / ".env").write_text("MEMORY_OS_AI_ENABLED=false\n", encoding="utf-8")
    saved = backup_storage(root, database, root / "knowledge", "0006")
    backup_configuration(root, saved)
    return root, saved


def test_complete_copy_preserves_configuration_vault_and_empty_directories(backup, tmp_path):
    root, saved = backup
    target = tmp_path / "恢复副本"
    result = restore_new(saved, target)
    assert result["ai_rag_started"] is False
    assert (target / "knowledge/empty").is_dir()
    for name in [".env", "config/ai-providers.yml", "knowledge/.memory-os-vault", "knowledge/中文 空格.md"]:
        assert (target / name).read_bytes() == (root / name).read_bytes()
    with pytest.raises(ValueError, match="new"):
        restore_new(saved, target)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "knowledge/../escape", "knowledge\\bad", "knowledge/NUL.md"])
def test_invalid_manifest_never_creates_destination(backup, tmp_path, name):
    _, saved = backup
    manifest = json.loads((saved / "manifest.json").read_text("utf-8"))
    manifest["files"][0]["path"] = name
    (saved / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        restore_new(saved, tmp_path / "target")
    assert not (tmp_path / "target").exists()


@pytest.mark.parametrize("mode", ["tamper", "missing_config", "extra_vault", "duplicate", "missing_marker"])
def test_corrupt_or_incomplete_backups_are_rejected(backup, mode):
    _, saved = backup
    if mode == "tamper":
        (saved / "knowledge/中文 空格.md").write_text("changed", encoding="utf-8")
    elif mode == "missing_config":
        (saved / "configuration/.env").unlink()
    elif mode == "extra_vault":
        (saved / "knowledge/unlisted.md").write_text("unlisted", encoding="utf-8")
    elif mode == "duplicate":
        path = saved / "manifest.json"
        path.write_text(path.read_text("utf-8").replace('"database": "memory.db"', '"database": "memory.db", "database": "memory.db"'), encoding="utf-8")
    else:
        (saved / "knowledge/.memory-os-vault").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_backup(saved)
