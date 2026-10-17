"""Ordered provenance, legacy compatibility and all-source lifecycle checks."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.schemas import KnowledgeCreate, KnowledgePatch, KnowledgeRestore
from app.models import Knowledge, KnowledgeSource, Source
from app.repositories.database import Database
from app.services.content import ContentService
from sqlalchemy.orm.exc import StaleDataError


def source(client, title="source"):
    response = client.post("/api/v1/sources", json={"title": title})
    assert response.status_code == 201
    return response.json()


def test_multi_source_create_order_filter_and_delete_guard(client, settings):
    first, second = source(client, "first"), source(client, "second")
    response = client.post("/api/v1/knowledge", json={"title": "combined", "source_ids": [first["id"], second["id"]]})
    assert response.status_code == 201, response.text
    note = response.json()
    assert note["version"] == 1
    assert note["source_id"] == first["id"] and note["source_ids"] == [first["id"], second["id"]]
    for identity in note["source_ids"]:
        assert client.get("/api/v1/knowledge", params={"source_id": identity}).json()["total"] == 1
        summary = client.get("/api/v1/ui/knowledge", params={"source_id": identity}).json()
        assert summary["total"] == 1 and summary["items"][0]["source_ids"] == note["source_ids"]
        assert "body" not in summary["items"][0]
        assert client.delete(f"/api/v1/sources/{identity}", params={"expected_version": 1}).status_code == 409
    patched = client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": 1,
        "source_ids": [second["id"], first["id"]]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2 and patched.json()["source_id"] == second["id"]
    database = Database(settings.database_url)
    database.initialize()
    with database.session() as session:
        rows = session.scalars(select(KnowledgeSource).where(KnowledgeSource.knowledge_id == note["id"])
                               .order_by(KnowledgeSource.position)).all()
        assert [(row.source_id, row.position) for row in rows] == [(second["id"], 0), (first["id"], 1)]
    database.dispose()


def test_legacy_source_id_sets_one_and_detaches_all(client):
    first, second = source(client), source(client)
    note = client.post("/api/v1/knowledge", json={"title": "legacy", "source_id": first["id"]}).json()
    assert note["source_ids"] == [first["id"]]
    note = client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": note["version"],
        "source_ids": [first["id"], second["id"]]}).json()
    note = client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": note["version"], "source_id": second["id"]}).json()
    assert note["source_ids"] == [second["id"]]
    note = client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": note["version"], "source_id": None}).json()
    assert note["source_ids"] == [] and note["source_id"] is None


def test_restore_checks_every_source_and_allows_explicit_detach(client):
    first, second = source(client), source(client)
    note = client.post("/api/v1/knowledge", json={"title": "combined", "source_ids": [first["id"], second["id"]]}).json()
    deleted = client.delete(f"/api/v1/knowledge/{note['id']}", params={"expected_version": note["version"]}).json()
    assert client.delete(f"/api/v1/sources/{second['id']}", params={"expected_version": 1}).status_code == 200
    assert client.post(f"/api/v1/knowledge/{note['id']}/restore", json={"expected_version": deleted["version"]}).status_code == 409
    response = client.post(f"/api/v1/knowledge/{note['id']}/restore", json={"expected_version": deleted["version"], "source_ids": []})
    assert response.status_code == 200, response.text
    assert response.json()["source_ids"] == [] and not response.json()["deleted"]


@pytest.mark.parametrize("payload", [
    {"source_ids": None}, {"source_ids": [str(uuid4())] * 2},
    {"source_ids": [str(uuid4()) for _ in range(21)]},
    {"source_ids": [], "source_id": str(uuid4())},
    {"source_ids": [str(uuid4())], "source_id": None},
])
def test_invalid_association_fields_rejected_without_writes(client, payload):
    before = client.get("/api/v1/knowledge").json()["total"]
    response = client.post("/api/v1/knowledge", json={"title": "invalid", **payload})
    assert response.status_code == 422
    assert client.get("/api/v1/knowledge").json()["total"] == before


def test_missing_secondary_source_is_atomic_and_twenty_sources_supported(client):
    identities = [source(client)["id"] for _ in range(20)]
    response = client.post("/api/v1/knowledge", json={"title": "20 sources", "source_ids": identities})
    assert response.status_code == 201 and response.json()["source_ids"] == identities
    bad = client.post("/api/v1/knowledge", json={"title": "invalid", "source_ids": [identities[0], str(uuid4())]})
    assert bad.status_code == 409
    assert client.get("/api/v1/knowledge").json()["total"] == 1


def test_deleted_note_can_only_change_associations_then_restore(client):
    first, second = source(client), source(client)
    note = client.post("/api/v1/knowledge", json={"title": "combined", "source_ids": [first["id"], second["id"]]}).json()
    note = client.delete(f"/api/v1/knowledge/{note['id']}", params={"expected_version": note["version"]}).json()
    assert client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": note["version"], "title": "wrong"}).status_code == 409
    changed = client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": note["version"], "source_ids": [second["id"]]}).json()
    assert changed["deleted"] and changed["source_ids"] == [second["id"]]
    assert client.post(f"/api/v1/knowledge/{note['id']}/restore", json={"expected_version": note["version"]}).status_code == 409


def test_source_arrays_normalize_uuid_and_reject_explicit_mismatch():
    identity = uuid4()
    for model, values in [(KnowledgeCreate, {"title": "x"}), (KnowledgePatch, {"expected_version": 1}),
                          (KnowledgeRestore, {"expected_version": 1})]:
        result = model.model_validate({**values, "source_ids": [identity.hex.upper()]})
        assert result.source_ids == [str(identity)] and result.source_id == str(identity)


def test_stale_transaction_rolls_back_association_replacement(client):
    first, second, third = [source(client) for _ in range(3)]
    note = client.post("/api/v1/knowledge", json={"title": "combined", "source_ids": [first["id"], second["id"]]}).json()
    with client.app.state.database.session() as stale:
        stale_note = stale.get(Knowledge, note["id"])
        assert stale_note.source_ids == [first["id"], second["id"]]
        assert client.patch(f"/api/v1/knowledge/{note['id']}", json={"expected_version": 1, "source_ids": [third["id"]]}).status_code == 200
        with pytest.raises(StaleDataError):
            ContentService(stale).update_knowledge(note["id"], 1, {"source_ids": []})
            stale.commit()
        stale.rollback()
    current = client.get(f"/api/v1/knowledge/{note['id']}").json()
    assert current["source_ids"] == [third["id"]] and current["version"] == 2


def test_association_foreign_keys_position_bounds_and_uniqueness(client):
    first, second, third = [source(client) for _ in range(3)]
    note = client.post("/api/v1/knowledge", json={"title": "combined", "source_ids": [first["id"], second["id"]]}).json()
    with client.app.state.database.session() as session:
        with pytest.raises(IntegrityError):
            session.execute(delete(Source).where(Source.id == second["id"]))
            session.commit()
        session.rollback()
        for identity, position in [(third["id"], 0), (third["id"], -1), (third["id"], 20), (str(uuid4()), 2)]:
            session.add(KnowledgeSource(knowledge_id=note["id"], source_id=identity, position=position))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    assert client.get(f"/api/v1/knowledge/{note['id']}").json()["source_ids"] == [first["id"], second["id"]]
