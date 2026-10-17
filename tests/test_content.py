"""Source/Knowledge CRUD, soft deletion, revisions and durable sync intent."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Knowledge, Source, SyncOperation, SyncState


def new_source(client: TestClient, **values) -> dict:
    response = client.post("/api/v1/sources", json={"title": "原始资料", **values})
    assert response.status_code == 201, response.text
    return response.json()


def new_note(client: TestClient, **values) -> dict:
    response = client.post("/api/v1/knowledge", json={"title": "知识笔记", **values})
    assert response.status_code == 201, response.text
    return response.json()


def test_source_crud_soft_delete_restore_and_revision(client: TestClient) -> None:
    source = new_source(client, content="Original text", author="作者")
    assert source["source_type"] == "manual"
    assert source["version"] == 1
    assert source["created_at"].endswith("+00:00")
    response = client.patch(f"/api/v1/sources/{source['id']}", json={
        "expected_version": 1, "title": "更新标题", "author": None,
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["version"] == 2
    assert updated["author"] is None
    assert client.patch(f"/api/v1/sources/{source['id']}", json={
        "expected_version": 1, "content": "Stale overwrite",
    }).status_code == 409
    assert client.delete(f"/api/v1/sources/{source['id']}?expected_version=1").status_code == 409
    response = client.delete(f"/api/v1/sources/{source['id']}?expected_version=2")
    assert response.status_code == 200
    deleted = response.json()
    assert deleted["deleted_at"] is not None
    assert deleted["version"] == 3
    assert client.get(f"/api/v1/sources/{source['id']}").status_code == 404
    assert client.get(f"/api/v1/sources/{source['id']}?include_deleted=true").status_code == 200
    restored = client.post(f"/api/v1/sources/{source['id']}/restore", json={"expected_version": 3})
    assert restored.status_code == 200
    assert restored.json()["version"] == 4
    assert restored.json()["deleted_at"] is None


def test_knowledge_fields_and_pending_state_do_not_write_files(
    client: TestClient, isolated_project: Path,
) -> None:
    note = new_note(client, body="# 正文\n内容", summary="摘要", category="数据库",
                    tags=["SQL"], concepts=["transaction"])
    assert note["source_id"] is None
    assert note["sync_status"] == "pending"
    assert note["deleted"] is False
    with client.app.state.database.session() as session:
        assert session.get(SyncState, note["id"]).status == "pending"
    assert not list((isolated_project / "knowledge").glob("**/*.md"))
    changed = client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": note["version"], "tags": [], "body": "New text", "category": None,
    })
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert changed.json()["tags"] == []
    assert changed.json()["category"] is None
    stale = client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": 1, "body": "Old text",
    })
    assert stale.status_code == 409
    assert client.get(f"/api/v1/knowledge/{note['id']}").json()["body"] == "New text"


def test_source_can_have_multiple_notes_and_cannot_delete_while_active(client: TestClient) -> None:
    source = new_source(client)
    first = new_note(client, source_id=source["id"])
    second = new_note(client, source_id=source["id"])
    page = client.get("/api/v1/knowledge", params={"source_id": source["id"]}).json()
    assert page["total"] == 2
    assert {note["id"] for note in page["items"]} == {first["id"], second["id"]}
    assert client.delete(f"/api/v1/sources/{source['id']}?expected_version=1").status_code == 409
    client.delete(f"/api/v1/knowledge/{first['id']}?expected_version=1")
    assert client.delete(f"/api/v1/sources/{source['id']}?expected_version=1").status_code == 409
    client.delete(f"/api/v1/knowledge/{second['id']}?expected_version=1")
    assert client.delete(f"/api/v1/sources/{source['id']}?expected_version=1").status_code == 200


def test_knowledge_delete_records_a_durable_operation_and_keeps_source(client: TestClient) -> None:
    source = new_source(client)
    note = new_note(client, source_id=source["id"], body="Recoverable body")
    with client.app.state.database.session() as session:
        state = session.get(SyncState, note["id"])
        state.path = "nested/笔记.md"
        state.file_hash = "a" * 64
        session.commit()
    response = client.delete(f"/api/v1/knowledge/{note['id']}?expected_version=1")
    assert response.status_code == 200
    deleted = response.json()
    assert deleted["version"] == 2
    assert deleted["deleted"] is True
    assert client.get(f"/api/v1/knowledge/{note['id']}").status_code == 404
    assert client.get(f"/api/v1/knowledge/{note['id']}?include_deleted=true").json()["body"] == "Recoverable body"
    with client.app.state.database.session() as session:
        operation = session.scalar(select(SyncOperation).where(SyncOperation.knowledge_id == note["id"]))
        assert operation.kind == "delete"
        assert operation.path == "nested/笔记.md"
        assert operation.expected_hash == "a" * 64
        assert operation.expected_version == 2
        assert operation.target_snapshot["body"] == "Recoverable body"
        assert operation.target_snapshot["deleted"] is True
        assert session.get(Source, source["id"]).deleted_at is None


def test_restore_deleted_note_can_detach_deleted_source(client: TestClient) -> None:
    source = new_source(client)
    note = new_note(client, source_id=source["id"])
    client.delete(f"/api/v1/knowledge/{note['id']}?expected_version=1")
    client.delete(f"/api/v1/sources/{source['id']}?expected_version=1")
    assert client.post(f"/api/v1/knowledge/{note['id']}/restore", json={"expected_version": 2}).status_code == 409
    restored = client.post(f"/api/v1/knowledge/{note['id']}/restore", json={
        "expected_version": 2, "source_id": None,
    })
    assert restored.status_code == 200
    assert restored.json()["source_id"] is None
    assert restored.json()["deleted_at"] is None
    assert restored.json()["version"] == 3


def test_deleted_note_only_allows_source_reassignment_until_restored(client: TestClient) -> None:
    source = new_source(client)
    note = new_note(client, source_id=source["id"])
    client.delete(f"/api/v1/knowledge/{note['id']}?expected_version=1")
    assert client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": 2, "body": "Must restore first",
    }).status_code == 409
    changed = client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": 2, "source_id": None,
    })
    assert changed.status_code == 200
    assert changed.json()["version"] == 3
    assert changed.json()["deleted"] is True


def test_create_and_patch_reject_missing_or_deleted_source(client: TestClient) -> None:
    assert client.post("/api/v1/knowledge", json={
        "title": "Invalid source", "source_id": str(uuid4()),
    }).status_code == 409
    source = new_source(client)
    client.delete(f"/api/v1/sources/{source['id']}?expected_version=1")
    assert client.post("/api/v1/knowledge", json={
        "title": "Deleted source", "source_id": source["id"],
    }).status_code == 409
    note = new_note(client)
    assert client.patch(f"/api/v1/knowledge/{note['id']}", json={
        "expected_version": 1, "source_id": source["id"],
    }).status_code == 409


def test_pagination_and_deleted_visibility(client: TestClient) -> None:
    first = new_note(client, title="First")
    new_note(client, title="Second")
    new_note(client, title="Third")
    page = client.get("/api/v1/knowledge?offset=1&limit=1").json()
    assert page["total"] == 3
    assert page["offset"] == 1
    assert page["limit"] == 1
    assert len(page["items"]) == 1
    client.delete(f"/api/v1/knowledge/{first['id']}?expected_version=1")
    assert client.get("/api/v1/knowledge").json()["total"] == 2
    assert client.get("/api/v1/knowledge?include_deleted=true").json()["total"] == 3
    assert client.get("/api/v1/knowledge?limit=101").status_code == 422
    assert client.get("/api/v1/sources?offset=-1").status_code == 422


@pytest.mark.parametrize("payload", [
    {}, {"title": "   "}, {"title": "Title", "tags": "not-a-list"},
    {"title": "Title", "source_id": "bad-id"}, {"title": "Title", "unexpected": True},
])
def test_invalid_note_input_is_rejected(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/knowledge", json=payload).status_code == 422


@pytest.mark.parametrize("payload", [
    {"body": "No version"}, {"expected_version": 1},
    {"expected_version": 1, "title": None}, {"expected_version": 1, "tags": None},
])
def test_patch_requires_version_and_non_null_required_fields(client: TestClient, payload: dict) -> None:
    note = new_note(client)
    assert client.patch(f"/api/v1/knowledge/{note['id']}", json=payload).status_code == 422


def test_delete_requires_current_version_and_restore_checks_it(client: TestClient) -> None:
    note = new_note(client)
    assert client.delete(f"/api/v1/knowledge/{note['id']}").status_code == 422
    assert client.delete(f"/api/v1/knowledge/{note['id']}?expected_version=2").status_code == 409
    client.delete(f"/api/v1/knowledge/{note['id']}?expected_version=1")
    assert client.post(f"/api/v1/knowledge/{note['id']}/restore", json={"expected_version": 1}).status_code == 409
