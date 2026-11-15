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
    saved = backup_storage(root, database, root / "knowledge", "0009")
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


def test_restored_prompt_draft_and_paused_task_never_resume_model_calls(backup, tmp_path):
    from fastapi.testclient import TestClient
    from app.agents.configuration import AIProfile
    from app.config import Settings
    from app.main import create_app
    from app.models import ProcessingBatch, ProcessingBatchItem, ProcessingRun
    from app.desktop.update import _legacy_snapshot
    from app.services.processing_records import input_hash
    from scripts.local_rag_support import ForbiddenGeneration

    root, _ = backup
    database = root / "data/memory.db"
    settings = Settings(_env_file=None, runtime_root=root,
                        database_url=f"sqlite:///{database.as_posix()}", sync_enabled=False)
    forbidden = ForbiddenGeneration()
    with TestClient(create_app(settings, model_client=forbidden)) as client:
        source = client.post("/api/v1/sources", json={"title": "恢复任务", "content": "自编证据"}).json()
        prompt = client.app.state.processing.templates.snapshot()
        profile = AIProfile(protocol="openai_chat", base_url="http://127.0.0.1:1", model="isolated", auth="none").model_dump()
        with client.app.state.database.session() as session:
            run = ProcessingRun(source_id=source["id"], source_version=source["version"],
                source_snapshot=source, source_snapshots=[source], input_hash=input_hash(source),
                profile_id="isolated", protocol="openai_chat", model="isolated", config_fingerprint=input_hash(profile),
                prompt_version=str(prompt["version"]), prompt_hash=prompt["content_hash"], prompt_snapshot=prompt,
                output_schema_version=prompt["output_schema_version"], status="interrupted", usage={"output_tokens": 13})
            batch = ProcessingBatch(client_request_id="recovery-only", request_hash=input_hash(source),
                mode="individual", status="paused", profile_id="isolated", model="isolated", profile_snapshot=profile,
                prompt_snapshot=prompt, generation_settings={}, source_snapshots=[source])
            session.add_all([run, batch])
            session.flush()
            session.add(ProcessingBatchItem(batch_id=batch.id, position=0, source_ids=[source["id"]],
                status="interrupted", run_id=run.id, run_ids=[run.id], attempts=1))
            session.commit()
            run_id, batch_id = run.id, batch.id
    before = _legacy_snapshot(database)
    saved = backup_storage(root, database, root / "knowledge", "0009")
    backup_configuration(root, saved)
    target = tmp_path / "task-restored"
    restore_new(saved, target)
    restored_db = target / "data/memory.db"
    assert _legacy_snapshot(restored_db) == before
    restored_settings = settings.model_copy(update={"runtime_root": target, "database_url": f"sqlite:///{restored_db.as_posix()}"})
    with TestClient(create_app(restored_settings, model_client=forbidden)) as client:
        assert client.get(f"/api/v1/processing/runs/{run_id}").json()["status"] == "interrupted"
        task = client.get(f"/api/v1/processing/batches/{batch_id}").json()
        assert task["status"] == "paused" and task["items"][0]["attempts"] == 1
    assert forbidden.calls == 0
