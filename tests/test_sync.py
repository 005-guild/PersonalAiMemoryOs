"""Real database/vault reconciliation with fixed clocks and recoverable failures."""

from pathlib import Path
from threading import RLock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Knowledge, Source, SyncConflict, SyncOperation, SyncState
from app.repositories.database import Database
from app.services import sync as sync_module
from app.services import sync_operations
from app.services.content import ContentService
from app.services.markdown import NoteDocument, parse_document, raw_hash, render_document
from app.services.sync import MARKER, Synchronizer


class VaultHarness:
    """Exercise business transactions and independent synchronization sessions."""

    def __init__(self, database: Database, settings: Settings):
        self.database, self.settings = database, settings
        self.sync = Synchronizer(database, settings, RLock())
        self.root = settings.knowledge_path

    def call(self, method: str, *args, **kwargs):
        with self.database.session() as session:
            result = getattr(ContentService(session), method)(*args, **kwargs)
            session.commit()
            return result

    def create(self, **values) -> dict:
        return self.call("create_knowledge", {"title": "Note", "body": "original", **values})

    def update(self, identifier: str, **values) -> dict:
        return self.call("update_knowledge", identifier, self.note(identifier).version, values)

    def note(self, identifier: str) -> Knowledge:
        with self.database.session() as session:
            return session.get(Knowledge, identifier)

    def state(self, identifier: str) -> SyncState:
        with self.database.session() as session:
            return session.get(SyncState, identifier)

    def records(self, model) -> list:
        with self.database.session() as session:
            return list(session.scalars(select(model)))

    def run(self, now: float = 100) -> dict:
        status = self.sync.run_once(now=now)
        assert status["last_error"] is None, status
        return status

    def settle(self, now: float = 100) -> dict:
        self.run(now)
        return self.run(now)

    def export(self, **values) -> tuple[dict, Path]:
        note = self.create(**values)
        self.run()
        path = self.root / self.state(note["id"]).path
        assert path.is_file()
        self.settle()
        return note, path

    def edit_file(self, path: Path, **values) -> str:
        doc = parse_document(path.read_bytes().decode("utf-8"))
        content = render_document(doc.model_copy(update=values))
        path.write_bytes(content.encode("utf-8"))
        return content


@pytest.fixture
def vault(settings: Settings):
    database = Database(settings.database_url)
    database.initialize()
    harness = VaultHarness(database, settings)
    try:
        harness.run(now=0)
        yield harness
    finally:
        database.dispose()


def test_new_database_note_exports_immediately_and_api_changes_export(vault: VaultHarness) -> None:
    note = vault.create(body="abc")

    vault.run()
    state = vault.state(note["id"])
    path = vault.root / state.path

    assert parse_document(path.read_text(encoding="utf-8")).body == "abc"
    assert parse_document(path.read_text(encoding="utf-8")).id == note["id"]
    assert state.status == "synced"
    vault.settle()
    updated = vault.update(note["id"], body="API edit", tags=["tag"])
    vault.run()

    document = parse_document(path.read_text(encoding="utf-8"))
    assert document.body == "API edit"
    assert document.tags == ["tag"]
    assert vault.note(note["id"]).version == updated["version"]
    assert vault.records(SyncConflict) == []


def test_external_edit_requires_two_identical_scans_and_preserves_source(vault: VaultHarness) -> None:
    source = vault.call("create_source", {"source_type": "manual", "title": "Source", "content": "raw"})
    note, path = vault.export(source_id=source["id"])
    edited = vault.edit_file(path, body="Markdown edit", title="Edited", summary="Summary")

    vault.run()
    assert vault.note(note["id"]).body == "original"
    vault.run()

    current = vault.note(note["id"])
    assert (current.title, current.body, current.summary) == ("Edited", "Markdown edit", "Summary")
    assert current.version == 2
    assert path.read_text(encoding="utf-8") == edited
    assert vault.records(Source)[0].content == "raw"
    assert vault.state(note["id"]).status == "synced"


def test_equal_dual_edits_and_frontmatter_reformat_do_not_conflict(vault: VaultHarness) -> None:
    note, path = vault.export()
    updated = vault.update(note["id"], body="same edit")
    vault.edit_file(path, body="same edit")
    vault.settle()

    assert vault.note(note["id"]).version == updated["version"]
    assert vault.records(SyncConflict) == []
    original = path.read_text(encoding="utf-8")
    path.write_bytes(original.replace("title: Note", "title: 'Note'").replace("\n", "\r\n").encode("utf-8"))
    vault.settle()

    assert vault.note(note["id"]).version == updated["version"]
    assert vault.records(SyncConflict) == []


def test_external_new_note_gets_identity_once_after_two_scans(vault: VaultHarness) -> None:
    path = vault.root / "external.md"
    path.write_text(render_document(NoteDocument(title="External", body="abc")), encoding="utf-8")

    vault.run()
    assert vault.records(Knowledge) == []
    vault.run()
    identifier = parse_document(path.read_text(encoding="utf-8")).id
    vault.settle()

    assert identifier is not None
    assert len(vault.records(Knowledge)) == 1
    assert vault.note(identifier).source_id is None
    assert vault.note(identifier).body == "abc"
    assert vault.state(identifier).path == "external.md"


def test_source_supports_multiple_notes_and_api_reassociation(vault: VaultHarness) -> None:
    first = vault.call("create_source", {"source_type": "manual", "title": "First"})
    second = vault.call("create_source", {"source_type": "manual", "title": "Second"})
    one, path = vault.export(source_id=first["id"])
    two, _ = vault.export(source_id=first["id"])

    vault.update(one["id"], source_id=second["id"])
    vault.run()

    assert parse_document(path.read_text(encoding="utf-8")).source_id == second["id"]
    assert vault.note(two["id"]).source_id == first["id"]
    assert vault.records(SyncConflict) == []


def test_external_source_reassociation_is_rejected_without_overwrite(vault: VaultHarness) -> None:
    source = vault.call("create_source", {"source_type": "manual", "title": "Source"})
    note, path = vault.export()
    changed_content = vault.edit_file(path, source_id=source["id"], body="external")

    vault.settle()

    assert vault.note(note["id"]).source_id is None
    assert vault.note(note["id"]).body == "original"
    assert vault.state(note["id"]).last_error == "source_id_is_managed_by_api"
    assert path.read_text(encoding="utf-8") == changed_content


def test_renaming_and_moving_preserves_identity_and_revision(vault: VaultHarness) -> None:
    note, old_path = vault.export()
    moved_path = vault.root / "nested" / "renamed.md"
    moved_path.parent.mkdir()
    old_path.rename(moved_path)

    vault.settle()

    assert vault.state(note["id"]).path == "nested/renamed.md"
    assert vault.note(note["id"]).version == 1
    assert vault.note(note["id"]).deleted_at is None
    assert not old_path.exists()
    assert vault.records(SyncConflict) == []


def test_file_deletion_needs_grace_and_multiple_clean_scans_then_restore(vault: VaultHarness) -> None:
    note, path = vault.export()
    path.unlink()

    vault.run(now=200)
    assert vault.state(note["id"]).missing_count == 1
    vault.run(now=209)
    assert vault.note(note["id"]).deleted_at is None
    vault.run(now=210)
    deleted = vault.note(note["id"])
    assert deleted.deleted_at is not None
    assert deleted.body == "original"
    assert vault.state(note["id"]).status == "deleted"

    vault.call("restore_knowledge", note["id"], deleted.version, {})
    vault.run(now=211)

    assert path.is_file()
    assert parse_document(path.read_text(encoding="utf-8")).body == "original"
    assert vault.note(note["id"]).deleted_at is None


def test_reappearing_confirmed_deleted_file_restores_note(vault: VaultHarness) -> None:
    note, path = vault.export()
    original = path.read_bytes()
    path.unlink()
    vault.run(now=200)
    vault.run(now=210)
    assert vault.note(note["id"]).deleted_at is not None

    path.write_bytes(original)
    vault.settle(now=211)

    assert vault.note(note["id"]).deleted_at is None
    assert vault.state(note["id"]).status == "synced"


def test_restart_resets_missing_grace_instead_of_deleting_immediately(vault: VaultHarness) -> None:
    note, path = vault.export()
    path.unlink()
    vault.run(now=200)
    vault.sync = Synchronizer(vault.database, vault.settings, RLock())

    vault.run(now=1000)
    assert vault.note(note["id"]).deleted_at is None
    assert vault.state(note["id"]).missing_since == 1000
    assert vault.state(note["id"]).missing_count == 1
    vault.run(now=1009)
    assert vault.note(note["id"]).deleted_at is None
    vault.run(now=1010)
    assert vault.note(note["id"]).deleted_at is not None


def test_divergent_edits_preserve_all_conflict_snapshots(vault: VaultHarness) -> None:
    note, path = vault.export()
    vault.update(note["id"], body="database edit")
    external_content = vault.edit_file(path, body="Markdown edit")

    vault.settle()
    first = vault.records(SyncConflict)[0]
    vault.settle()

    assert len(vault.records(SyncConflict)) == 1
    assert first.base["body"] == "original"
    assert first.db_snapshot["body"] == "database edit"
    assert first.file_snapshot["body"] == "Markdown edit"
    assert first.file_content == external_content
    assert first.file_hash == raw_hash(external_content)
    assert vault.note(note["id"]).body == "database edit"
    assert path.read_text(encoding="utf-8") == external_content

    vault.edit_file(path, body="second Markdown edit")
    vault.settle()
    conflicts = vault.records(SyncConflict)
    old = next(conflict for conflict in conflicts if conflict.id == first.id)
    current = next(conflict for conflict in conflicts if conflict.status == "open")
    assert old.status == "superseded"
    assert old.file_snapshot["body"] == "Markdown edit"
    assert current.file_snapshot["body"] == "second Markdown edit"


def test_database_delete_vs_external_edit_preserves_file_and_conflict(vault: VaultHarness) -> None:
    note, path = vault.export()
    vault.call("delete_knowledge", note["id"], note["version"])
    edited = vault.edit_file(path, body="do not remove")

    vault.settle()

    conflict = next(conflict for conflict in vault.records(SyncConflict) if conflict.status == "open")
    assert conflict.db_snapshot["deleted"] is True
    assert conflict.file_snapshot["body"] == "do not remove"
    assert path.read_text(encoding="utf-8") == edited
    assert vault.note(note["id"]).deleted_at is not None


def test_database_edit_vs_file_delete_is_a_conflict(vault: VaultHarness) -> None:
    note, path = vault.export()
    vault.update(note["id"], body="keep database edit")
    path.unlink()

    vault.run(now=200)

    conflict = vault.records(SyncConflict)[0]
    assert conflict.db_snapshot["body"] == "keep database edit"
    assert conflict.file_snapshot is None
    assert conflict.reason == "edit_vs_file_delete"
    assert vault.note(note["id"]).deleted_at is None
    assert not path.exists()


@pytest.mark.parametrize("mode", ["duplicate", "unknown"])
def test_duplicate_or_unknown_ids_never_overwrite_or_import(vault: VaultHarness, mode: str) -> None:
    note, path = vault.export()
    document = parse_document(path.read_text(encoding="utf-8"))
    if mode == "unknown":
        document = document.model_copy(update={"id": str(uuid4())})
    extra = vault.root / "extra.md"
    content = render_document(document.model_copy(update={"body": "preserve extra"}))
    extra.write_text(content, encoding="utf-8")

    status = vault.settle()

    assert any(issue["code"] == f"{mode}_id" for issue in status["issues"])
    assert len(vault.records(Knowledge)) == 1
    assert vault.note(note["id"]).body == "original"
    assert extra.read_text(encoding="utf-8") == content


def test_identity_write_failure_does_not_register_the_same_file_again(
    vault: VaultHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = vault.root / "external.md"
    path.write_text(render_document(NoteDocument(title="External")), encoding="utf-8")
    original_write = sync_operations.atomic_write

    def denied(*args, **kwargs):
        raise PermissionError("simulated identity write failure")

    monkeypatch.setattr(sync_operations, "atomic_write", denied)
    vault.settle()
    notes = vault.records(Knowledge)
    assert len(notes) == 1
    assert parse_document(path.read_text(encoding="utf-8")).id is None
    vault.run()
    assert len(vault.records(Knowledge)) == 1

    monkeypatch.setattr(sync_operations, "atomic_write", original_write)
    vault.settle()

    assert len(vault.records(Knowledge)) == 1
    assert parse_document(path.read_text(encoding="utf-8")).id == notes[0].id
    assert vault.state(notes[0].id).status == "synced"


def test_restart_recovers_file_write_completed_before_database_ack(
    vault: VaultHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedCrash(BaseException):
        pass

    note = vault.create(body="must survive")

    def crash(*args):
        raise SimulatedCrash()

    monkeypatch.setattr(vault.sync.journal, "_complete", crash)
    with pytest.raises(SimulatedCrash):
        vault.sync.run_once(now=100)
    path = vault.root / f"{note['id']}.md"
    assert parse_document(path.read_text(encoding="utf-8")).body == "must survive"
    assert vault.records(SyncOperation)[0].status == "pending"

    vault.database.dispose()
    vault.database.initialize()
    vault.sync = Synchronizer(vault.database, vault.settings, RLock())
    vault.settle(now=101)

    assert len(vault.records(Knowledge)) == 1
    assert vault.note(note["id"]).version == 1
    assert vault.records(SyncOperation)[0].status == "applied"
    assert vault.state(note["id"]).status == "synced"
    assert vault.records(SyncConflict) == []


def test_scan_failure_never_applies_partial_deletions(
    vault: VaultHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    note, path = vault.export()
    path.unlink()
    vault.run(now=200)

    def denied(*args):
        raise PermissionError("simulated scan failure")

    monkeypatch.setattr(sync_module, "scan_files", denied)
    for now in (210, 300):
        status = vault.sync.run_once(now=now)
        assert status["last_error"] == "PermissionError"
        assert vault.note(note["id"]).deleted_at is None


@pytest.mark.parametrize("loss", ["directory", "marker", "invalid_marker"])
def test_vault_loss_pauses_without_recreation_or_database_deletion(vault: VaultHarness, loss: str) -> None:
    note, path = vault.export()
    if loss == "directory":
        vault.root.rename(vault.root.with_name("moved-vault"))
    elif loss == "marker":
        (vault.root / MARKER).unlink()
    else:
        (vault.root / MARKER).write_text(str(uuid4()), encoding="utf-8")

    status = vault.sync.run_once(now=10000)

    assert status["last_error"] is not None
    assert vault.note(note["id"]).deleted_at is None
    if loss == "directory":
        assert not vault.root.exists()
    else:
        assert path.is_file()


@pytest.mark.parametrize("choice", ["database", "markdown"])
def test_conflict_api_resolves_selected_snapshot_and_preserves_history(client, choice: str) -> None:
    response = client.post("/api/v1/knowledge", json={"title": "Conflict", "body": "base"})
    assert response.status_code == 201, response.text
    note = response.json()
    sync = client.app.state.synchronizer
    for _ in range(3):
        assert sync.run_once(now=100)["last_error"] is None
    with client.app.state.database.session() as session:
        path = sync.root / session.get(SyncState, note["id"]).path
    client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": 1, "body": "database"})
    doc = parse_document(path.read_text(encoding="utf-8"))
    path.write_text(render_document(doc.model_copy(update={"body": "markdown"})), encoding="utf-8")
    sync.run_once(now=101)
    sync.run_once(now=102)
    conflicts = client.get("/api/v1/sync/conflicts").json()
    assert conflicts["total"] == 1
    conflict = conflicts["items"][0]

    resolved = client.post(f"/api/v1/sync/conflicts/{conflict['id']}/resolve", json={"choice": choice})

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["body"] == choice
    assert parse_document(path.read_text(encoding="utf-8")).body == choice
    assert client.get("/api/v1/sync/conflicts").json()["total"] == 0
    preserved = client.get(f"/api/v1/sync/conflicts/{conflict['id']}").json()
    assert preserved["status"] == "resolved"
    assert preserved["base"]["body"] == "base"
    assert preserved["db_snapshot"]["body"] == "database"
    assert preserved["file_snapshot"]["body"] == "markdown"
    assert client.post(f"/api/v1/sync/conflicts/{conflict['id']}/resolve", json={"choice": choice}).status_code == 409


def test_conflict_api_rejects_resolution_after_unobserved_file_change(client) -> None:
    note = client.post("/api/v1/knowledge", json={"title": "Conflict", "body": "base"}).json()
    sync = client.app.state.synchronizer
    for _ in range(3):
        sync.run_once(now=100)
    with client.app.state.database.session() as session:
        path = sync.root / session.get(SyncState, note["id"]).path
    client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": 1, "body": "database"})
    doc = parse_document(path.read_text(encoding="utf-8"))
    path.write_text(render_document(doc.model_copy(update={"body": "first external"})), encoding="utf-8")
    sync.run_once(now=101)
    sync.run_once(now=102)
    conflict = client.get("/api/v1/sync/conflicts").json()["items"][0]
    latest = render_document(doc.model_copy(update={"body": "unobserved external"}))
    path.write_text(latest, encoding="utf-8")

    response = client.post(f"/api/v1/sync/conflicts/{conflict['id']}/resolve", json={"choice": "database"})

    assert response.status_code == 409
    assert path.read_text(encoding="utf-8") == latest
    current = client.get("/api/v1/sync/conflicts").json()["items"][0]
    assert current["id"] != conflict["id"]
    assert current["file_snapshot"]["body"] == "unobserved external"
    old = client.get(f"/api/v1/sync/conflicts/{conflict['id']}").json()
    assert old["status"] == "superseded"
    assert old["file_snapshot"]["body"] == "first external"


def test_open_conflict_blocks_a_later_api_delete_operation(vault: VaultHarness) -> None:
    note, path = vault.export()
    vault.update(note["id"], body="database edit")
    original_file = vault.edit_file(path, body="Markdown edit")
    vault.settle()
    assert vault.state(note["id"]).status == "conflict"

    vault.call("delete_knowledge", note["id"], vault.note(note["id"]).version)
    vault.settle()

    assert path.read_text(encoding="utf-8") == original_file
    conflict = next(row for row in vault.records(SyncConflict) if row.status == "open")
    assert conflict.db_snapshot["deleted"] is True
    assert conflict.file_snapshot["body"] == "Markdown edit"
    deletion = next(row for row in vault.records(SyncOperation) if row.kind == "delete")
    assert deletion.status != "applied"
    assert vault.state(note["id"]).status == "conflict"


def test_restoring_note_never_overwrites_a_path_occupied_by_another_identity(vault: VaultHarness) -> None:
    original, original_path = vault.export(body="restore original")
    vault.call("delete_knowledge", original["id"], original["version"])
    vault.run()
    assert not original_path.exists()
    occupant, occupant_path = vault.export(body="occupant content")
    occupant_path.rename(original_path)
    expected = original_path.read_bytes()

    vault.call("restore_knowledge", original["id"], vault.note(original["id"]).version, {})
    vault.settle()

    assert original_path.read_bytes() == expected
    assert parse_document(expected.decode("utf-8")).id == occupant["id"]
    assert vault.note(original["id"]).body == "restore original"
    assert vault.note(occupant["id"]).body == "occupant content"
    assert not occupant_path.exists()


def test_database_unavailability_is_reported_without_status_raising(vault: VaultHarness) -> None:
    note, path = vault.export()
    original = path.read_bytes()
    vault.database.dispose()

    status = vault.sync.run_once(now=1000)

    assert status["last_error"] == "RuntimeError"
    assert status["counts"] == {}
    assert status["notes"] == []
    assert path.read_bytes() == original


def test_conflict_resolution_after_unobserved_rename_requires_review(client) -> None:
    note = client.post("/api/v1/knowledge", json={"title": "Conflict", "body": "base"}).json()
    sync = client.app.state.synchronizer
    for _ in range(3):
        sync.run_once(now=100)
    with client.app.state.database.session() as session:
        old_path = sync.root / session.get(SyncState, note["id"]).path
    client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": 1, "body": "database"})
    doc = parse_document(old_path.read_text(encoding="utf-8"))
    old_path.write_text(render_document(doc.model_copy(update={"body": "markdown"})), encoding="utf-8")
    sync.run_once(now=101)
    sync.run_once(now=102)
    conflict = client.get("/api/v1/sync/conflicts").json()["items"][0]
    moved_path = sync.root / "moved.md"
    old_path.rename(moved_path)

    response = client.post(f"/api/v1/sync/conflicts/{conflict['id']}/resolve", json={"choice": "database"})

    assert response.status_code == 409
    assert not old_path.exists()
    assert parse_document(moved_path.read_text(encoding="utf-8")).body == "markdown"
    latest = client.get("/api/v1/sync/conflicts").json()["items"][0]
    assert latest["file_path"] == "moved.md"
    assert latest["id"] != conflict["id"]


def test_selecting_markdown_content_retains_api_managed_source_association(client) -> None:
    first = client.post("/api/v1/sources", json={"title": "First source"}).json()
    second = client.post("/api/v1/sources", json={"title": "Second source"}).json()
    note = client.post("/api/v1/knowledge", json={
        "title": "Conflict", "source_id": first["id"], "body": "base",
    }).json()
    sync = client.app.state.synchronizer
    for _ in range(3):
        sync.run_once(now=100)
    with client.app.state.database.session() as session:
        path = sync.root / session.get(SyncState, note["id"]).path
    client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": 1, "source_id": second["id"], "body": "database",
    })
    doc = parse_document(path.read_text(encoding="utf-8"))
    path.write_text(render_document(doc.model_copy(update={"body": "markdown"})), encoding="utf-8")
    sync.run_once(now=101)
    sync.run_once(now=102)
    conflict = client.get("/api/v1/sync/conflicts").json()["items"][0]

    response = client.post(f"/api/v1/sync/conflicts/{conflict['id']}/resolve", json={"choice": "markdown"})

    assert response.status_code == 200, response.text
    assert response.json()["body"] == "markdown"
    assert response.json()["source_id"] == second["id"]
    rendered = parse_document(path.read_text(encoding="utf-8"))
    assert rendered.body == "markdown"
    assert rendered.source_id == second["id"]


def test_restoring_archive_after_detaching_deleted_source_rewrites_header(client) -> None:
    source_response = client.post("/api/v1/sources", json={"title": "Archived source"})
    assert source_response.status_code == 201
    source = source_response.json()
    note_response = client.post("/api/v1/knowledge", json={
        "title": "Archived note", "source_id": source["id"], "body": "Archived body",
    })
    assert note_response.status_code == 201
    note = note_response.json()
    sync = client.app.state.synchronizer
    for _ in range(3):
        assert sync.run_once(now=100)["last_error"] is None
    with client.app.state.database.session() as session:
        path = sync.root / session.get(SyncState, note["id"]).path
    archived = path.read_bytes()
    assert parse_document(archived.decode("utf-8")).source_id == source["id"]

    deleted = client.delete(
        f"/api/v1/knowledge/{note['id']}", params={"expected_version": note["version"]}
    )
    assert deleted.status_code == 200
    assert sync.run_once(now=101)["last_error"] is None
    assert not path.exists()
    assert client.delete(
        f"/api/v1/sources/{source['id']}", params={"expected_version": source["version"]}
    ).status_code == 200
    detached = client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": deleted.json()["version"], "source_id": None,
    })
    assert detached.status_code == 200
    assert detached.json()["deleted"] is True
    assert detached.json()["source_id"] is None
    assert sync.run_once(now=102)["last_error"] is None
    with client.app.state.database.session() as session:
        assert session.get(SyncState, note["id"]).base["source_id"] == source["id"]

    path.write_bytes(archived)
    for now in (103, 104, 105, 106):
        assert sync.run_once(now=now)["last_error"] is None

    restored = client.get(f"/api/v1/knowledge/{note['id']}")
    assert restored.status_code == 200
    assert restored.json()["deleted"] is False
    assert restored.json()["source_id"] is None
    assert restored.json()["body"] == "Archived body"
    assert restored.json()["sync_status"] == "synced"
    header = parse_document(path.read_bytes().decode("utf-8"))
    assert header.id == note["id"]
    assert header.source_id is None
    assert header.body == "Archived body"
    assert client.get("/api/v1/sync/conflicts").json()["total"] == 0
