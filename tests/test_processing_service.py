"""Drafts survive failures while adoption remains versioned and atomic."""

import asyncio
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.agents.errors import AIError
from app.models import Knowledge, ProcessingRun, Source, SyncState
from app.repositories.database import Database
from app.services.content import ContentError, ContentService
from app.services.processing import ProcessingFailure, ProcessingService

VALID_RESULT = {
    "title": "学习笔记", "summary": "保留来源信息。", "category": "知识管理",
    "tags": ["笔记"], "concepts": ["来源"], "key_points": ["资料应保留原文。"],
    "opinions": [{"statement": "保留原文有助于核验。", "evidence": "保留原文",
                  "analysis": "笔记和原始资料应分别维护。"}],
}


class Registry:
    settings = SimpleNamespace(ai_max_input_chars=20000)

    def resolve(self, profile_id=None):
        return SimpleNamespace(profile_id=profile_id or "test-profile", fingerprint="a" * 64,
                               profile=SimpleNamespace(protocol="openai_chat", model="test-model"))


class Model:
    def __init__(self):
        self.calls = 0
        self.error = None
        self.result = copy.deepcopy(VALID_RESULT)

    async def generate(self, resolved, system_prompt, user_prompt):
        self.calls += 1
        assert json.loads(user_prompt)["content"]
        if self.error:
            raise self.error
        return SimpleNamespace(text=json.dumps(self.result, ensure_ascii=False),
                               usage={"input_tokens": 20, "output_tokens": 40})


@pytest.fixture
def context(migrated_database):
    database = Database(migrated_database)
    database.initialize()
    model = Model()
    service = ProcessingService(database, RLock(), Registry(), model)
    with database.session() as session:
        source = ContentService(session).create_source({
            "source_type": "manual", "title": "原始资料", "author": "作者",
            "url": "https://example.com/source", "content": "必须保留原文。\n方便核验。",
        })
        session.commit()
    yield SimpleNamespace(database=database, model=model, service=service, source=source)
    database.dispose()


def generate(context, **kwargs):
    return asyncio.run(context.service.generate(context.source["id"], context.source["version"], **kwargs))


def count(context, model):
    with context.database.session() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_generation_preserves_snapshot_and_does_not_create_knowledge(context):
    run = generate(context)
    assert run["status"] == "ready" and run["version"] == 2
    assert not run["source_stale"]
    assert run["source_snapshot"]["content"] == context.source["content"]
    assert run["result"] == VALID_RESULT
    assert run["proposal"]["source_id"] == context.source["id"]
    assert "原文依据：" in run["proposal"]["body"]
    assert len(run["input_hash"]) == len(run["prompt_hash"]) == 64
    assert run["usage"] == {"input_tokens": 20, "output_tokens": 40}
    assert count(context, Knowledge) == count(context, SyncState) == 0
    assert context.service.get_run(run["id"]) == run
    page = context.service.list_runs(source_id=context.source["id"], status="ready", profile_id="test-profile")
    assert page["total"] == 1 and page["offset"] == 0 and page["limit"] == 20
    assert page["items"][0]["id"] == run["id"]
    assert not {"source_snapshot", "result", "proposal"}.intersection(page["items"][0])
    assert context.service.list_runs(status="failed")["total"] == 0


def test_adoption_is_idempotent_and_does_not_restore_deleted_note(context):
    run = generate(context)
    adopted = context.service.adopt(run["id"], run["version"])
    assert not adopted["already_adopted"]
    assert adopted["run"]["status"] == "adopted" and adopted["run"]["version"] == 3
    assert adopted["knowledge"]["source_id"] == context.source["id"]
    assert adopted["knowledge"]["sync_status"] == "pending"
    note_id = adopted["knowledge"]["id"]
    with context.database.session() as session:
        ContentService(session).delete_knowledge(note_id, 1)
        session.commit()
    again = context.service.adopt(run["id"], 1)
    assert again["already_adopted"] and again["knowledge"]["id"] == note_id
    assert again["knowledge"]["deleted_at"] is not None
    assert count(context, Knowledge) == count(context, SyncState) == 1


def test_parallel_adoption_creates_exactly_one_knowledge(context):
    run = generate(context)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: context.service.adopt(run["id"], run["version"]), range(2)))
    assert {result["knowledge"]["id"] for result in results} == {results[0]["knowledge"]["id"]}
    assert sorted(result["already_adopted"] for result in results) == [False, True]
    assert count(context, Knowledge) == 1


def test_stale_draft_version_prevents_adoption(context):
    run = generate(context)
    with pytest.raises(ContentError) as error:
        context.service.adopt(run["id"], 1)
    assert error.value.status_code == 409
    assert count(context, Knowledge) == 0


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_source_changes_are_visible_and_prevent_adoption(context, change):
    run = generate(context)
    with context.database.session() as session:
        content = ContentService(session)
        if change == "edit":
            content.update_source(context.source["id"], 1, {"content": "Updated source"})
        else:
            content.delete_source(context.source["id"], 1)
        session.commit()
    assert context.service.get_run(run["id"])["source_stale"]
    with pytest.raises(ContentError) as error:
        context.service.adopt(run["id"], run["version"])
    assert error.value.status_code == 409
    assert count(context, Knowledge) == 0


@pytest.mark.parametrize("failure,status", [("missing", 404), ("deleted", 409), ("stale", 409),
                                           ("blank", 422), ("oversize", 422)])
def test_invalid_sources_never_register_or_call_model(context, failure, status):
    source_id, version = context.source["id"], 1
    if failure == "missing":
        source_id = "missing"
    elif failure == "stale":
        version = 7
    else:
        with context.database.session() as session:
            content = ContentService(session)
            if failure == "deleted":
                content.delete_source(source_id, 1)
            else:
                content.update_source(source_id, 1, {"content": " \n " if failure == "blank" else "x" * 20001})
                version = 2
            session.commit()
    with pytest.raises(ContentError) as error:
        asyncio.run(context.service.generate(source_id, version))
    assert error.value.status_code == status
    assert count(context, ProcessingRun) == context.model.calls == 0
    # Every rejected preflight releases the one-call semaphore.
    assert context.service._gate.acquire(blocking=False)
    context.service._gate.release()


@pytest.mark.parametrize("status,code", [(502, "upstream_error"), (504, "upstream_timeout")])
def test_model_errors_leave_queryable_failed_run_without_raw_data(context, status, code):
    context.model.error = AIError(status, code)
    with pytest.raises(ProcessingFailure) as failure:
        generate(context)
    assert failure.value.status_code == status and failure.value.code == code
    run = context.service.get_run(failure.value.run_id)
    assert run["status"] == "failed" and run["error_code"] == code
    assert run["result"] is None and run["proposal"] is None and run["finished_at"]
    assert count(context, Knowledge) == 0
    with pytest.raises(ContentError) as error:
        context.service.adopt(run["id"], run["version"])
    assert error.value.status_code == 409
    context.model.error = None
    assert generate(context)["status"] == "ready"


def test_invalid_evidence_is_a_failed_draft(context):
    context.model.result["opinions"][0]["evidence"] = "Never appeared in source"
    with pytest.raises(ProcessingFailure) as failure:
        generate(context)
    assert failure.value.code == "invalid_evidence"
    assert context.service.get_run(failure.value.run_id)["status"] == "failed"
    assert count(context, Knowledge) == 0


def test_adoption_commit_failure_rolls_back_note_and_run(context, monkeypatch):
    run = generate(context)
    factory = context.database.session

    def unavailable_session():
        session = factory()
        def unavailable_commit():
            raise RuntimeError("database unavailable including sensitive details")
        session.commit = unavailable_commit
        return session

    with monkeypatch.context() as patch:
        patch.setattr(context.database, "session", unavailable_session)
        with pytest.raises(ProcessingFailure) as error:
            context.service.adopt(run["id"], run["version"])
        assert error.value.status_code == 503 and str(error.value) == "database_unavailable"
    assert count(context, Knowledge) == count(context, SyncState) == 0
    assert context.service.get_run(run["id"])["status"] == "ready"
    assert not context.service.adopt(run["id"], run["version"])["already_adopted"]


def test_adoption_race_recovery_database_failure_is_safe(context, monkeypatch):
    run = generate(context)
    context.service.adopt(run["id"], run["version"])
    attempts = 0
    def competing_adoption(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise StaleDataError("The other transaction already adopted this run.")
        raise RuntimeError("Database unavailable including sensitive details.")
    monkeypatch.setattr(context.service, "_adopt", competing_adoption)
    with pytest.raises(ProcessingFailure) as failure:
        context.service.adopt(run["id"], run["version"])
    assert failure.value.status_code == 503 and failure.value.code == "database_unavailable"
    assert failure.value.run_id == run["id"] and "sensitive" not in str(failure.value)
    assert attempts == 2 and count(context, Knowledge) == 1


def test_database_failure_after_model_keeps_run_for_restart_recovery(context, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("database unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(context.service, "_ready", unavailable)
        with pytest.raises(ProcessingFailure) as failure:
            generate(context)
        run_id = failure.value.run_id
        assert failure.value.status_code == 503
    assert context.service.get_run(run_id)["status"] == "running"
    context.service.recover_interrupted()
    recovered = context.service.get_run(run_id)
    assert recovered["status"] == "interrupted" and recovered["error_code"] == "interrupted"
    assert recovered["finished_at"] and recovered["version"] == 2
    context.service.recover_interrupted()
    assert context.service.get_run(run_id)["version"] == 2
    assert context.model.calls == 1 and count(context, Knowledge) == 0


def test_model_wait_holds_neither_sync_lock_nor_transaction(context):
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        original_generate = context.model.generate
        async def wait(*args):
            started.set()
            await release.wait()
            return await original_generate(*args)
        context.model.generate = wait
        first = asyncio.create_task(context.service.generate(context.source["id"], 1))
        await started.wait()
        with pytest.raises(ProcessingFailure) as error:
            await context.service.generate(context.source["id"], 1)
        assert error.value.status_code == 429
        def update():
            with context.service.lock, context.database.session() as session:
                ContentService(session).update_source(context.source["id"], 1, {"title": "Changed while waiting"})
                session.commit()
        await asyncio.wait_for(asyncio.to_thread(update), timeout=2)
        assert context.service.list_runs(status="running")["total"] == 1
        release.set()
        run = await first
        assert run["status"] == "ready" and run["source_stale"]
        assert run["source_snapshot"]["title"] == "原始资料"
        await context.service.close()
    asyncio.run(scenario())


def test_cancelled_caller_does_not_cancel_generation_and_shutdown_waits(context):
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        original_generate = context.model.generate
        async def wait(*args):
            started.set()
            await release.wait()
            return await original_generate(*args)
        context.model.generate = wait
        caller = asyncio.create_task(context.service.generate(context.source["id"], 1))
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        draining = asyncio.create_task(context.service.close())
        await asyncio.sleep(0)
        assert not draining.done()
        with pytest.raises(ProcessingFailure) as error:
            await context.service.generate(context.source["id"], 1)
        assert error.value.code == "processing_unavailable"
        release.set()
        await draining
        assert context.service.list_runs(status="ready")["total"] == 1
        assert context.model.calls == 1
    asyncio.run(scenario())


def test_lookup_and_list_database_failures_are_safe(context):
    context.database.dispose()
    for action in (lambda: context.service.get_run("missing"), context.service.list_runs):
        with pytest.raises(ProcessingFailure) as failure:
            action()
        assert failure.value.status_code == 503 and str(failure.value) == "database_unavailable"


def test_missing_run_returns_not_found(context):
    for action in (lambda: context.service.get_run("missing"), lambda: context.service.adopt("missing", 1)):
        with pytest.raises(ContentError) as error:
            action()
        assert error.value.status_code == 404
