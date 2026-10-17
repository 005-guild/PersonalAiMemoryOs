"""Purpose isolation, immutable QA snapshots, and bounded draft views."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
from threading import Event
from types import SimpleNamespace

from alembic import command
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.agents.generation_gate import GenerationGate
from app.models import ProcessingRun, PromptTemplate
from app.repositories.database import Database
from app.repositories.migrations import migration_config, upgrade_database
from app.services.prompt_templates import DEEP_ANALYSIS_ID, RAG_QA_ID
from app.services.rag_answer import RagAnswerService
from processing_v2_helpers import ai_batches, source, submit, wait_batch
from test_rag_answer import Model, Registry, Search

BASE = "/api/v1/prompt-templates"


def test_0005_migration_preserves_every_original_template_column(sqlite_url):
    database = Database(sqlite_url)
    database.initialize()
    with database.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "0005")
    row = {"id": DEEP_ANALYSIS_ID, "version": 7, "name": "Original", "description": "Original description",
           "content": "Unmodified original content", "content_hash": "a" * 64,
           "output_schema_version": 2, "is_default": 1, "archived_at": None,
           "created_at": "2026-10-01", "updated_at": "2026-10-02"}
    revision = {"template_id": row["id"], **{key: value for key, value in row.items()
        if key not in {"id", "is_default", "archived_at", "updated_at"}}}
    with database.engine.begin() as connection:
        for table, values in (("prompt_templates", row), ("prompt_revisions", revision)):
            columns = ",".join(values)
            connection.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({','.join(':' + key for key in values)})"), values)
    upgrade_database(sqlite_url)
    upgrade_database(sqlite_url)
    with database.engine.connect() as connection:
        for table, values in (("prompt_templates", row), ("prompt_revisions", revision)):
            record = connection.execute(text(f"SELECT * FROM {table}")).mappings().one()
            assert dict(record) == {**values, "purpose": "knowledge"}
    database.dispose()


def test_defaults_and_archives_are_independent_per_purpose(ai_batches):
    client, app, model = ai_batches
    original = client.get(f"{BASE}/{DEEP_ANALYSIS_ID}").json()
    qa = client.get(BASE + "?purpose=rag_qa").json()["items"][0]
    assert qa["id"] == RAG_QA_ID and qa["is_default"] and qa["purpose"] == "rag_qa"
    assert qa["output_schema_version"] == 1
    created = client.post(BASE, json={"name": "Precise QA", "content": "Answer in a table.", "purpose": "rag_qa"}).json()
    response = client.post(f"{BASE}/{created['id']}/default", json={"expected_version": 1})
    assert response.status_code == 200 and response.json()["is_default"]
    assert client.get(f"{BASE}/{DEEP_ANALYSIS_ID}").json() == original
    assert client.post(f"{BASE}/{RAG_QA_ID}/archive", json={"expected_version": 2}).status_code == 200
    assert client.patch(f"{BASE}/{created['id']}", json={"expected_version": 2, "purpose": "knowledge"}).status_code == 422
    assert client.patch(f"{BASE}/{created['id']}", json={"expected_version": 2, "output_schema_version": 2}).status_code == 422
    with app.state.database.session() as session:
        defaults = list(session.scalars(select(PromptTemplate).where(PromptTemplate.is_default.is_(True))))
        assert {row.purpose for row in defaults} == {"knowledge", "rag_qa"}
    assert model.calls == 0


def test_purpose_rejected_before_analysis_or_question_model_call(ai_batches):
    client, _, model = ai_batches
    selected = source(client)
    response = client.post("/api/v1/processing/runs", json={"source_id": selected["id"],
        "expected_source_version": 1, "prompt_template_id": RAG_QA_ID})
    assert response.status_code == 422
    response = client.post("/api/v1/rag/ask", json={"question": "What?", "prompt_template_id": DEEP_ANALYSIS_ID})
    assert response.status_code == 422
    assert model.calls == 0


@pytest.mark.parametrize("limit", [10, 20, 50, 100])
def test_template_search_and_revision_summary_pagination(ai_batches, limit):
    client, app, model = ai_batches
    for number in range(101):
        app.state.processing.templates.create({"name": f"Literal%_{number:03}", "content": "private body" * 20,
                                               "purpose": "rag_qa", "output_schema_version": 1})
    listing = client.get(BASE, params={"purpose": "rag_qa", "q": "Literal%_", "limit": limit,
                                      "offset": 1, "summary_only": True}).json()
    assert listing["total"] == 101 and len(listing["items"]) == min(limit, 100)
    assert all("content" not in row and row["purpose"] == "rag_qa" for row in listing["items"])
    first = listing["items"][0]
    client.patch(f"{BASE}/{first['id']}", json={"expected_version": 1, "content": "new body"})
    revisions = client.get(f"{BASE}/{first['id']}/revisions?offset=1&limit=10&summary_only=true").json()
    assert revisions["total"] == 2 and revisions["items"][0]["version"] == 1
    assert "content" not in revisions["items"][0]
    assert client.get(f"{BASE}/{first['id']}/revisions/1").json()["content"] == "private body" * 20
    assert model.calls == 0


def test_qa_freezes_selected_revision_and_keeps_fixed_contract(ai_batches):
    client, app, _ = ai_batches
    started, release = Event(), Event()

    class SlowModel(Model):
        async def generate(self, *args):
            started.set()
            assert await asyncio.to_thread(release.wait, 5)
            return await super().generate(*args)

    model = SlowModel()
    app.state.rag_answer = RagAnswerService(Search(), Registry(), model, GenerationGate())
    template = client.post(BASE, json={"name": "Chinese QA", "purpose": "rag_qa", "content": "Frozen style A"}).json()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(client.post, "/api/v1/rag/ask", json={"question": "How?",
            "prompt_template_id": template["id"], "prompt_template_version": 1})
        try:
            assert started.wait(5)
            assert client.patch(f"{BASE}/{template['id']}", json={"expected_version": 1,
                                "content": "New style B"}).status_code == 200
        finally:
            release.set()
        response = future.result()
    assert response.status_code == 200, response.text
    assert response.json()["prompt_template"]["version"] == 1
    assert "Frozen style A" in model.prompts[0][0] and "New style B" not in model.prompts[0][0]
    assert "insufficient_evidence" in model.prompts[0][0] and "没有联网能力" in model.prompts[0][0]
    assert model.calls == 1


def test_prompt_summary_pages_do_not_load_builtin_or_current_template_bodies(ai_batches):
    client, app, model = ai_batches
    statements = []
    def captured(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(app.state.database.engine, "before_cursor_execute", captured)
    try:
        assert client.get(BASE + "?summary_only=true").status_code == 200
        assert client.get(f"{BASE}/{DEEP_ANALYSIS_ID}/revisions?summary_only=true").status_code == 200
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", captured)
    assert not any(re.search(r"prompt_(?:templates|revisions)\.content\b", sql) for sql in statements)
    assert model.calls == 0


def test_draft_summaries_exclude_bodies_and_filter_on_secondary_source(ai_batches):
    client, app, _ = ai_batches
    sources = [source(client, number) for number in (1, 2)]
    batch = wait_batch(client, submit(client, sources, mode="merged")["id"])
    run_id = batch["items"][0]["run_id"]
    statements = []
    def captured(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(app.state.database.engine, "before_cursor_execute", captured)
    try:
        listing = client.get("/api/v1/ui/drafts", params={"source_id": sources[1]["id"],
            "prompt_template_id": DEEP_ANALYSIS_ID, "q": "八阶段", "limit": 10}).json()
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", captured)
    assert listing["total"] == 1
    draft = listing["items"][0]
    assert draft["id"] == run_id and draft["source_count"] == 2 and draft["prompt_template_id"] == DEEP_ANALYSIS_ID
    assert not ({"source_snapshot", "source_snapshots", "result", "proposal", "body", "content"} & draft.keys())
    assert all("processing_runs.result" not in sql and "processing_runs.source_snapshot," not in sql for sql in statements)
    run = client.get("/api/v1/processing/runs/" + run_id).json()
    client.post(f"/api/v1/processing/runs/{run_id}/adopt", json={"expected_version": run["version"]})
    assert client.get("/api/v1/ui/drafts?state=ready").json()["total"] == 0
    assert client.get("/api/v1/ui/drafts?state=adopted").json()["total"] == 1


def test_input_lengths_and_limit_error_are_actionable_before_call(ai_batches):
    client, app, model = ai_batches
    app.state.ai_registry.settings.ai_max_input_chars = 10
    created = client.post("/api/v1/sources", json={"title": "超长😀", "content": "中文😀" * 4}).json()
    assert client.get("/api/v1/ai/profiles").json()["max_input_chars"] == 10
    assert client.get("/api/v1/ui/sources").json()["items"][0]["content_chars"] == 12
    response = client.post("/api/v1/processing/batches", json={"client_request_id": "limit-test", "mode": "individual",
        "sources": [{"source_id": created["id"], "expected_version": 1}]})
    assert response.status_code == 422
    assert all(value in response.json()["detail"] for value in ("超长😀", created["id"], "12", "10"))
    assert client.get("/api/v1/processing/batches").json()["total"] == 0 and model.calls == 0
