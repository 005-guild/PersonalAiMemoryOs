"""Markdown v1 stays stable; v2 preserves ordered provenance through recovery."""

from threading import RLock
from uuid import uuid4

import pytest

from app.models import SyncConflict, SyncOperation
from app.services import sync_operations
from app.services.markdown import NoteDocument, content_hash, document_projection, parse_document, render_document
from app.services.sync import Synchronizer
from test_sync import VaultHarness, vault


def sources(vault):
    return [vault.call("create_source", {"title": title, "source_type": "manual"})["id"] for title in ("first", "second")]


def test_v1_render_projection_hash_unchanged():
    identity = str(uuid4())
    doc = NoteDocument(title="原有", source_id=identity, body="body\n")
    assert "source_ids" not in render_document(doc)
    expected = {"source_id": identity, "title": "原有", "body": "body\n", "summary": "", "category": None,
                "tags": [], "concepts": []}
    assert document_projection(doc) == expected
    assert content_hash(document_projection(doc)) == content_hash(expected)


def test_multi_source_v2_roundtrip_and_existing_v1_no_rewrite(vault):
    identities = sources(vault)
    old, old_path = vault.export(source_id=identities[0])
    old_bytes = old_path.read_bytes()
    multi, path = vault.export(source_ids=identities)
    doc = parse_document(path.read_text(encoding="utf-8"))
    assert doc.schema_version == 2 and doc.association_ids == identities
    assert doc.source_id == identities[0]
    assert document_projection(parse_document(render_document(doc))) == document_projection(doc)
    vault.settle()
    assert old_path.read_bytes() == old_bytes
    vault.edit_file(path, body="外部更新\n")
    vault.settle()
    note = vault.note(multi["id"])
    assert note.body == "外部更新\n" and note.source_ids == identities


def test_external_v2_new_identity_move_delete_restore(vault):
    identities = sources(vault)
    path = vault.root / "new.md"
    path.write_text(render_document(NoteDocument(schema_version=2, source_ids=identities, title="new", body="new body")), encoding="utf-8")
    vault.settle()
    doc = parse_document(path.read_text(encoding="utf-8"))
    assert doc.id and vault.note(doc.id).source_ids == identities
    moved = vault.root / "moved.md"
    path.rename(moved)
    vault.settle()
    assert vault.state(doc.id).path == "moved.md"
    archived = moved.read_bytes()
    moved.unlink()
    vault.run(now=110); vault.run(now=121)
    assert vault.note(doc.id).deleted_at is not None
    moved.write_bytes(archived)
    vault.settle(now=130)
    assert vault.note(doc.id).deleted_at is None and vault.note(doc.id).source_ids == identities


def test_source_change_in_file_rejected_even_if_primary_unchanged(vault):
    identities = sources(vault)
    third = vault.call("create_source", {"title": "third", "source_type": "manual"})["id"]
    note, path = vault.export(source_ids=identities)
    vault.edit_file(path, source_ids=[identities[0], third])
    vault.settle()
    assert vault.state(note["id"]).last_error == "source_ids_are_managed_by_api"
    assert vault.note(note["id"]).source_ids == identities


def test_multisource_conflict_choice_keeps_database_associations(vault):
    identities = sources(vault)
    note, path = vault.export(source_ids=identities)
    vault.update(note["id"], source_ids=list(reversed(identities)), body="db edit")
    vault.edit_file(path, body="file edit")
    vault.settle()
    conflict = next(item for item in vault.records(SyncConflict) if item.status == "open")
    assert conflict.db_snapshot["source_ids"] == list(reversed(identities))
    from app.services.sync_conflicts import ConflictResolver
    ConflictResolver(vault.sync).resolve(conflict.id, "markdown")
    assert vault.note(note["id"]).body == "file edit"
    assert parse_document(path.read_text(encoding="utf-8")).association_ids == list(reversed(identities))


def test_multisource_identity_write_failure_restart_is_idempotent(vault, monkeypatch):
    identities = sources(vault)
    path = vault.root / "new.md"
    path.write_text(render_document(NoteDocument(schema_version=2, source_ids=identities, title="new")), encoding="utf-8")
    original = sync_operations.atomic_write
    monkeypatch.setattr(sync_operations, "atomic_write", lambda *args: (_ for _ in ()).throw(OSError("synthetic")))
    vault.settle()
    assert len(vault.records(SyncOperation)) == 1
    identifier = vault.records(SyncOperation)[0].knowledge_id
    monkeypatch.setattr(sync_operations, "atomic_write", original)
    vault.sync = Synchronizer(vault.database, vault.settings, RLock())
    vault.settle()
    assert parse_document(path.read_text(encoding="utf-8")).id == identifier
    assert vault.note(identifier).source_ids == identities
    assert len(vault.records(SyncOperation)) == 1


def test_multisource_delete_failure_restart_and_archived_restore_keeps_all_sources(vault, monkeypatch):
    identities = sources(vault)
    note, path = vault.export(source_ids=identities)
    archived = path.read_bytes()
    original = sync_operations.remove_file
    monkeypatch.setattr(sync_operations, "remove_file", lambda *args: (_ for _ in ()).throw(OSError("synthetic")))
    deleted = vault.call("delete_knowledge", note["id"], note["version"])
    vault.run()
    assert path.exists() and deleted["source_ids"] == identities
    monkeypatch.setattr(sync_operations, "remove_file", original)
    vault.sync = Synchronizer(vault.database, vault.settings, RLock())
    vault.settle()
    assert not path.exists()
    path.write_bytes(archived)
    vault.settle()
    assert vault.note(note["id"]).deleted_at is None and vault.note(note["id"]).source_ids == identities


@pytest.mark.parametrize("values", [
    {"schema_version": 1, "source_ids": []}, {"schema_version": 2},
    {"schema_version": 2, "source_ids": [str(uuid4())] * 2},
    {"schema_version": 2, "source_ids": [str(uuid4()) for _ in range(21)]},
    {"schema_version": 2, "source_ids": [], "source_id": str(uuid4())},
])
def test_invalid_v2_source_metadata(values):
    with pytest.raises(ValueError):
        NoteDocument(title="invalid", **values)
