"""Exercise imports and knowledge workflows without touching formal storage."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from verification_support import PROJECT_ROOT, RunningApp, RunningMockModel, eventually, note_path
from import_verification import check_zhihu_import
from processing_verification import PROTOCOLS, check_processing, check_processing_persistence, write_profiles

API = "/api/v1"


def synced_file(app: RunningApp, note_id: str, content: str = "") -> Path:
    def exported():
        path = note_path(app.vault, note_id)
        return path if path and content in path.read_text(encoding="utf-8") else None

    path = eventually(exported)
    eventually(lambda: app.note(note_id)["sync_status"] == "synced")
    return path


def check_editor_workflow(app: RunningApp) -> str:
    print("Checking API creation/export and automatic editor creation/edit/move...", flush=True)
    source = app.api("POST", f"{API}/sources", {"title": "Verification source", "content": "Original"})
    note = app.api("POST", f"{API}/knowledge", {
        "title": "Verification knowledge", "source_id": source["id"], "body": "Initial body.\n",
    })
    note_id = note["id"]
    path = synced_file(app, note_id, "Initial body.")
    assert (app.vault / ".memory-os-vault").is_file()

    note = app.note(note_id)
    app.api("PATCH", f"{API}/knowledge/{note_id}", {
        "expected_version": note["version"], "body": "API edited body.\n",
    })
    path = synced_file(app, note_id, "API edited body.")
    path.write_text(path.read_text(encoding="utf-8") + "External editor edit.\n", encoding="utf-8")
    eventually(lambda: "External editor edit." in app.note(note_id)["body"])

    new_file = app.vault / "created-in-editor.md"
    new_file.write_text(
        "---\nschema_version: 1\ntitle: Editor-created note\n---\nEditor creation body.\n",
        encoding="utf-8",
    )

    def imported():
        return next((item for item in app.api("GET", f"{API}/knowledge")["items"]
                     if item["title"] == "Editor-created note"), None)

    external_note = eventually(imported)
    eventually(lambda: external_note["id"] in new_file.read_text(encoding="utf-8"))
    assert external_note["source_id"] is None

    moved = app.vault / "moved" / "same-note.md"
    moved.parent.mkdir()
    path.rename(moved)

    def move_recorded():
        with closing(sqlite3.connect(app.database)) as database:
            row = database.execute("SELECT path FROM sync_states WHERE knowledge_id=?", (note_id,)).fetchone()
        return row is not None and row[0] == "moved/same-note.md"

    eventually(move_recorded)
    assert app.note(note_id)["id"] == note_id

    print("Checking editor soft deletion/restoration and API deletion/restoration...", flush=True)
    saved_content = moved.read_text(encoding="utf-8")
    moved.unlink()
    eventually(lambda: app.note(note_id, include_deleted=True)["deleted"], timeout=40)
    moved.write_text(saved_content, encoding="utf-8")
    eventually(lambda: not app.note(note_id, include_deleted=True)["deleted"])
    restored_file = synced_file(app, note_id, "External editor edit.")
    current = app.note(note_id)
    app.api("DELETE", f"{API}/knowledge/{note_id}?expected_version={current['version']}")
    eventually(lambda: not restored_file.exists())
    deleted = app.note(note_id, include_deleted=True)
    app.api("POST", f"{API}/knowledge/{note_id}/restore", {"expected_version": deleted["version"]})
    synced_file(app, note_id, "External editor edit.")
    return note_id


def check_conflicts(app: RunningApp, note_id: str) -> None:
    print("Checking preserved conflict snapshots and both explicit resolution choices...", flush=True)
    app.stop()
    app.start(sync_enabled=False)
    for choice in ("database", "markdown"):
        # Two controlled scans establish observations without a polling race.
        app.api("POST", f"{API}/sync/run")
        app.api("POST", f"{API}/sync/run")
        current = app.note(note_id)
        path = note_path(app.vault, note_id)
        assert path is not None
        file_marker = f"Markdown contender for {choice}."
        database_marker = f"Database contender for {choice}."
        path.write_text(path.read_text(encoding="utf-8") + file_marker + "\n", encoding="utf-8")
        app.api("PATCH", f"{API}/knowledge/{note_id}", {
            "expected_version": current["version"], "body": database_marker + "\n",
        })
        app.api("POST", f"{API}/sync/run")
        app.api("POST", f"{API}/sync/run")
        conflicts = app.api("GET", f"{API}/sync/conflicts")["items"]
        conflict = next(item for item in conflicts if item["knowledge_id"] == note_id)
        details = app.api("GET", f"{API}/sync/conflicts/{conflict['id']}")
        assert database_marker in details["db_snapshot"]["body"]
        assert file_marker in details["file_snapshot"]["body"]
        app.api("POST", f"{API}/sync/conflicts/{conflict['id']}/resolve", {"choice": choice})
        chosen = database_marker if choice == "database" else file_marker
        assert chosen in app.note(note_id)["body"]
        assert chosen in path.read_text(encoding="utf-8")
        assert app.api("GET", f"{API}/sync/conflicts")["total"] == 0


def check_restart_recovery(app: RunningApp, note_id: str) -> None:
    print("Checking restart recovery of pending export and offline editor changes...", flush=True)
    pending = app.api("POST", f"{API}/knowledge", {
        "title": "Pending export on restart", "body": "Recovered pending export.\n",
    })
    assert note_path(app.vault, pending["id"]) is None
    marker = (app.vault / ".memory-os-vault").read_text(encoding="utf-8")
    app.stop()
    path = note_path(app.vault, note_id)
    assert path is not None
    path.write_text(path.read_text(encoding="utf-8") + "Offline recovery marker.\n", encoding="utf-8")
    app.start()
    synced_file(app, pending["id"], "Recovered pending export.")
    eventually(lambda: "Offline recovery marker." in app.note(note_id)["body"])
    assert (app.vault / ".memory-os-vault").read_text(encoding="utf-8") == marker
    app.stop()
    with closing(sqlite3.connect(app.database)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert "Offline recovery marker." in "\n".join(database.iterdump())


def main() -> int:
    cache = (PROJECT_ROOT / ".cache").resolve()
    if not cache.is_relative_to(PROJECT_ROOT.resolve()):
        raise RuntimeError("The verification cache must remain inside the project.")
    cache.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="local-validation-", dir=cache)).resolve()
    app = RunningApp(workspace)
    mock = RunningMockModel(workspace)
    try:
        print(f"Isolated verification workspace: {workspace}", flush=True)
        model_url = mock.start()
        ai_config = workspace / "config" / "ai-providers.yml"
        write_profiles(ai_config, model_url)
        app.ai_environment = {
            "MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_CONFIG_FILE": str(ai_config),
            "MEMORY_OS_AI_DEFAULT_PROFILE": "openai_chat",
            "MEMORY_OS_AI_KEYS__VERIFICATION": "verification-only-key",
        }
        app.migrate()
        app.start()
        check_zhihu_import(app)
        processing_state = check_processing(app)
        note_id = check_editor_workflow(app)
        check_conflicts(app, note_id)
        check_restart_recovery(app, note_id)
        app.start()
        check_processing_persistence(app, processing_state)
        records = [json.loads(line) for line in (workspace / "mock-requests.jsonl").read_text(encoding="utf-8").splitlines()]
        assert {record["protocol"] for record in records} == set(PROTOCOLS)
        assert len(records) == 4, "Restart/repeated adoption unexpectedly called the model again"
    except Exception:
        print(app.logs()[-12000:], file=sys.stderr)
        raise
    finally:
        app.stop()
        mock.stop()
        if workspace.parent != cache.resolve() or not workspace.name.startswith("local-validation-"):
            raise RuntimeError("Refusing cleanup outside the project verification cache.")
        shutil.rmtree(workspace)
    print("Local migration, Zhihu import, four model protocols, draft adoption, CRUD/sync, restart recovery, and cleanup passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
