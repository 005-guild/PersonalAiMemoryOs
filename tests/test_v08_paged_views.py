"""All dashboard collections are bounded; summary polling uses only metadata."""

import asyncio

import pytest
from sqlalchemy import event, select

from app.models import Knowledge, ProcessingRun, Source, SyncConflict, SyncState
from app.models.rag import RagNoteIndexState
from app.repositories.rag import RagRepository
from processing_v2_helpers import ai_batches, source, submit, wait_batch
from test_rag_index import rig, create_note, update_note


@pytest.mark.parametrize("limit", [10, 20, 50, 100])
def test_sync_metadata_pages_are_bounded_and_do_not_load_baselines(client, limit):
    database = client.app.state.database
    with database.session() as session:
        for number in range(105):
            note = Knowledge(title=f"Note {number}", body="Body that should stay in the detail API")
            session.add(note)
            session.flush()
            session.add(SyncState(knowledge_id=note.id, status="error", path=f"{number}.md",
                                  base={"body": "large baseline" * 1000}, last_error="write_failed"))
            session.add(SyncConflict(knowledge_id=note.id, db_snapshot={"body": "private full body"},
                db_version=1, reason="changed_both_sides", file_content="original body"))
        session.commit()
    client.app.state.synchronizer.issues = [{"path": f"{number}.md", "code": "invalid_markdown"} for number in range(105)]
    statements = []
    def captured(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(database.engine, "before_cursor_execute", captured)
    try:
        summary = client.get("/api/v1/sync/status?summary_only=true").json()
        notes = client.get(f"/api/v1/sync/notes?offset=5&limit={limit}&status=error").json()
        issues = client.get(f"/api/v1/sync/issues?offset=5&limit={limit}").json()
        conflicts = client.get(f"/api/v1/sync/conflicts?offset=5&limit={limit}&summary_only=true").json()
    finally:
        event.remove(database.engine, "before_cursor_execute", captured)
    assert summary["counts"] == {"error": 105} and summary["issue_count"] == 105
    assert "notes" not in summary and "issues" not in summary
    for page in (notes, issues, conflicts):
        assert page["total"] == 105 and len(page["items"]) == limit and page["offset"] == 5
    assert "base" not in notes["items"][0] and "db_snapshot" not in conflicts["items"][0]
    assert all("sync_states.base" not in sql and "sync_conflicts.db_snapshot" not in sql for sql in statements)


def test_rag_light_summary_matches_published_failed_and_excluded_counts(rig, monkeypatch):
    published = create_note(rig)
    failed = create_note(rig, "Separate failing note")
    excluded = create_note(rig, "Deleted note")
    with rig.database.session() as session:
        session.get(Knowledge, excluded["id"]).deleted_at = "2026-10-01"
        session.commit()
    rig.embeddings.fail_at = 2
    asyncio.run(rig.indexer.run_once())
    complete = rig.indexer.status()
    assert complete["counts"]["published"] == 1 and complete["counts"]["failed"] == 1
    monkeypatch.setattr(RagRepository, "notes", lambda *args: (_ for _ in ()).throw(AssertionError("full notes loaded")))
    monkeypatch.setattr(RagRepository, "valid_chunks", lambda *args: (_ for _ in ()).throw(AssertionError("vector chunks loaded")))
    summary = rig.indexer.status(summary_only=True)
    assert summary["counts"] == complete["counts"] and summary["index_incomplete"] == complete["index_incomplete"]
    assert "errors" not in summary and "excluded" not in summary
    assert rig.indexer.details("errors", offset=0, limit=10)["total"] >= 1
    page = rig.indexer.details("excluded", offset=0, limit=10)
    assert page["total"] == 1 and page["items"][0]["reason"] == "deleted"
    with rig.database.session() as session:
        published_id = session.scalar(select(RagNoteIndexState.knowledge_id).where(RagNoteIndexState.status == "published"))
    published = next(note for note in (published, failed) if note["id"] == published_id)
    update_note(rig, published, body="Changed after publishing")
    assert rig.indexer.status(summary_only=True)["counts"]["published"] == 0


def test_batch_metadata_item_and_attempt_pages_keep_full_outputs_in_detail(ai_batches):
    client, app, _ = ai_batches
    batch = wait_batch(client, submit(client, [source(client, number) for number in range(20)])["id"])
    summary = client.get(f"/api/v1/processing/batches/{batch['id']}?summary_only=true").json()
    assert summary["counts"]["ready"] == 20
    assert not ({"items", "source_snapshots", "profile_snapshot", "prompt_snapshot"} & summary.keys())
    statements = []
    def captured(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(app.state.database.engine, "before_cursor_execute", captured)
    try:
        page = client.get(f"/api/v1/processing/batches/{batch['id']}/items?offset=10&limit=10").json()
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", captured)
    assert all("processing_batch_items.run_ids" not in statement for statement in statements)
    assert page["total"] == 20 and len(page["items"]) == 10 and page["items"][0]["position"] == 10
    assert "run_ids" not in page["items"][0]
    assert "content" not in page["items"][0]["sources"][0]
    item = page["items"][0]
    attempts = client.get(f"/api/v1/processing/batches/{batch['id']}/items/{item['id']}/attempts?limit=10").json()
    assert attempts["total"] == 1 and attempts["items"][0]["id"] == item["run_id"]
    assert "result" not in attempts["items"][0]
    old = client.get("/api/v1/processing/runs?limit=100").json()
    new = client.get("/api/v1/processing/runs?limit=100&summary_only=true").json()
    assert old == new
    selected = source(client, 999)
    assert client.get(f"/api/v1/processing/runs?summary_only=true&source_id={selected['id']}").json()["total"] == 0


def test_history_light_projection_matches_legacy_null_and_multi_source_staleness(ai_batches):
    client, app, model = ai_batches
    sources = [source(client, number) for number in (1, 2)]
    batch = wait_batch(client, submit(client, sources, mode="merged")["id"])
    identifier = batch["items"][0]["run_id"]
    with app.state.database.session() as session:
        session.get(Source, sources[1]["id"]).title = "Changed after generation"
        session.commit()
    old = client.get("/api/v1/processing/runs?limit=100").json()
    new = client.get("/api/v1/processing/runs?limit=100&summary_only=true").json()
    assert old == new and new["items"][0]["source_stale"]
    with app.state.database.session() as session:
        session.get(ProcessingRun, identifier).source_snapshots = None
        session.commit()
    old = client.get("/api/v1/processing/runs?limit=100").json()
    new = client.get("/api/v1/processing/runs?limit=100&summary_only=true").json()
    assert old == new and new["items"][0]["source_count"] == 1 and not new["items"][0]["source_stale"]


@pytest.mark.parametrize("path", ["/api/v1/prompt-templates", "/api/v1/ui/drafts", "/api/v1/sync/issues",
                                  "/api/v1/sync/notes", "/api/v1/rag/index/errors", "/api/v1/rag/index/excluded"])
def test_paged_endpoints_reject_unbounded_or_negative_inputs(client, path):
    assert client.get(path + "?limit=101").status_code == 422
    assert client.get(path + "?limit=0").status_code == 422
    assert client.get(path + "?offset=-1").status_code == 422
