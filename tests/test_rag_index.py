"""Publication, paid-call boundaries, and restart recovery use isolated SQLite."""

import asyncio
from threading import RLock
from types import SimpleNamespace

import pytest
from sqlalchemy import select
import yaml

from app.models import Knowledge, Source, SyncConflict, SyncState, utcnow
from app.models.rag import RagIndexGeneration, RagIndexJob, RagNoteIndexState
from app.repositories.database import Database
from app.services.content import ContentService
from app.services.rag_index import RagIndexService
from app.services.rag_search import RagSearchService
from app.vector.configuration import EmbeddingRegistry
from app.vector.errors import RagError


class Embeddings:
    def __init__(self):
        self.calls = []
        self.fail_at = None
        self.hook = None

    async def embed(self, resolved, texts):
        self.calls.append(texts)
        if self.hook:
            await self.hook(texts)
        if len(self.calls) == self.fail_at:
            raise RagError(504, "embedding_timeout")
        return SimpleNamespace(vectors=[[1.0, 0.25, 0.5] for _ in texts], usage={"total_tokens": 3})


class Qdrant:
    def __init__(self):
        self.collections = {}
        self.metadata = {}
        self.fail_upload = False
        self.fail_delete = False
        self.unavailable = False

    async def ensure_collection(self, name, dimension, metadata, create=True):
        if self.unavailable:
            raise RagError(503, "qdrant_unavailable")
        if name not in self.collections:
            if not create:
                raise RagError(503, "qdrant_collection_missing")
            self.collections[name], self.metadata[name] = {}, metadata
        if self.metadata[name] != metadata:
            raise RagError(409, "qdrant_collection_ownership_mismatch")
        assert dimension == 3

    async def upsert(self, name, points):
        self.collections[name].update({point["id"]: point for point in points})
        if self.fail_upload:
            raise RagError(503, "qdrant_timeout")

    async def query(self, name, vector, limit):
        return [{"id": point["id"], "score": 0.9, "payload": point["payload"]}
                for point in list(self.collections[name].values())[:limit]]

    async def delete_points(self, name, ids):
        if self.fail_delete:
            raise RagError(503, "qdrant_delete_timeout")
        for identity in ids:
            self.collections[name].pop(identity, None)

    async def delete_collection(self, name, metadata):
        if name in self.collections:
            assert self.metadata[name] == metadata
            self.collections.pop(name)


@pytest.fixture
def rig(settings, isolated_project):
    directory = isolated_project / "config"
    directory.mkdir()
    (directory / "embedding-providers.yml").write_text(yaml.safe_dump({
        "schema_version": 1, "default_profile": "fake", "profiles": {"fake": {
            "model": "deterministic", "base_url": "https://example.invalid/v1", "auth": "none",
            "dimension": 3, "batch_size": 2,
        }}
    }), encoding="utf-8")
    settings = settings.model_copy(update={"rag_enabled": True, "rag_chunk_chars": 100,
                                            "rag_chunk_overlap": 20})
    database = Database(settings.database_url)
    database.initialize()
    registry, embeddings, qdrant = EmbeddingRegistry(settings), Embeddings(), Qdrant()
    lock = RLock()
    indexer = RagIndexService(database, lock, settings, registry, embeddings, qdrant)
    search = RagSearchService(indexer, registry, embeddings, qdrant)
    value = SimpleNamespace(settings=settings, database=database, registry=registry,
                            embeddings=embeddings, qdrant=qdrant, lock=lock, indexer=indexer, search=search)
    yield value
    database.dispose()


def create_note(rig, body="正文包含恢复演练", **values):
    with rig.lock, rig.database.session() as session:
        note = ContentService(session).create_knowledge({"title": "恢复知识", "body": body, **values})
        session.commit()
        return note


def update_note(rig, note, **values):
    with rig.lock, rig.database.session() as session:
        note = ContentService(session).update_knowledge(note["id"], note["version"], values)
        session.commit()
        return note


def test_empty_index_is_available_without_embedding_a_query(rig):
    async def scenario():
        await rig.indexer.run_once()
        assert await rig.search.search("不存在") == {"items": [], "index_incomplete": False}
    asyncio.run(scenario())
    assert rig.embeddings.calls == []


def test_batched_intentions_are_committed_before_remote_call(rig):
    note = create_note(rig, "连续中文正文" * 80)
    observed = []
    async def hook(texts):
        def check():
            with rig.lock, rig.database.session() as session:
                job = session.scalars(select(RagIndexJob).where(RagIndexJob.status == "embedding")).one()
                assert job.intents[-1]["status"] == "calling"
                assert len(job.intents[-1]["indices"]) == len(texts) <= 2
                observed.append(job.id)
        await asyncio.to_thread(check)
    rig.embeddings.hook = hook
    asyncio.run(rig.indexer.run_once())
    assert len(observed) >= 3
    with rig.database.session() as session:
        state = session.get(RagNoteIndexState, (rig.indexer.status()["generation"]["id"], note["id"]))
        job = session.get(RagIndexJob, state.published_job_id)
        assert state.status == job.status == "published"
        assert all(intent["status"] == "succeeded" for intent in job.intents)
        assert all(vector is not None for vector in job.vectors)


def test_move_refreshes_reference_without_reembedding(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        with rig.database.session() as session:
            session.get(SyncState, note["id"]).path = "移动/知识.md"
            session.commit()
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        result = await rig.search.search("恢复")
        assert result["items"][0]["path"] == "移动/知识.md"
    asyncio.run(scenario())


def test_edit_filters_old_points_immediately_and_publishes_new_version(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        updated = update_note(rig, note, body="新的可靠正文")
        with pytest.raises(RagError, match="rag_index_not_ready"):
            await rig.search.search("恢复")
        assert rig.indexer.status()["index_incomplete"] is True
        await rig.indexer.run_once()
        items = (await rig.search.search("可靠"))["items"]
        assert items[0]["version"] == updated["version"]
        assert "新的可靠正文" in items[0]["text"]
        with rig.database.session() as session:
            jobs = list(session.scalars(select(RagIndexJob).order_by(RagIndexJob.created_at)))
            assert jobs[0].vectors is None and jobs[-1].vectors is not None
    asyncio.run(scenario())


def test_delete_restore_reuses_current_content_cache(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        with rig.database.session() as session:
            deleted = ContentService(session).delete_knowledge(note["id"], note["version"])
            session.commit()
        assert (await rig.search.search("恢复"))["items"] == []
        await rig.indexer.run_once()
        with rig.database.session() as session:
            ContentService(session).restore_knowledge(note["id"], deleted["version"], {})
            session.commit()
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        assert (await rig.search.search("恢复"))["items"]
    asyncio.run(scenario())


@pytest.mark.parametrize("block", ["sync_error", "conflict"])
def test_sync_block_excludes_hits_and_retains_reusable_cache(rig, block):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        with rig.database.session() as session:
            state = session.get(SyncState, note["id"])
            if block == "conflict":
                session.add(SyncConflict(knowledge_id=note["id"], db_snapshot={}, db_version=1,
                                         reason="concurrent_edit", status="open"))
            else:
                state.status, state.last_error = "error", "bad_file"
            session.commit()
        result = await rig.search.search("恢复")
        assert result["items"] == [] and result["index_incomplete"]
        await rig.indexer.run_once()
        with rig.database.session() as session:
            state = session.get(SyncState, note["id"])
            state.status, state.last_error = "pending", None
            for conflict in session.scalars(select(SyncConflict)):
                conflict.status = "resolved"
            session.commit()
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        assert (await rig.search.search("恢复"))["items"]
    asyncio.run(scenario())


def test_failed_call_is_never_automatically_retried_including_rebuild(rig):
    create_note(rig)
    rig.embeddings.fail_at = 1
    async def scenario():
        await rig.indexer.run_once()
        await rig.indexer.run_once()
        await rig.indexer.run_once(rebuild=True)
        rig.indexer.recover_interrupted()
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == 1
        assert rig.indexer.status()["counts"]["failed"] == 1
        await rig.indexer.run_once(retry_failed=True)
        assert len(rig.embeddings.calls) == 2
        assert rig.indexer.status()["counts"]["published"] == 1
        await rig.indexer.run_once(rebuild=True)
        assert len(rig.embeddings.calls) == 2
    asyncio.run(scenario())


def test_partial_batch_failure_only_retries_missing_vectors_explicitly(rig):
    create_note(rig, "长文正文" * 80)
    rig.embeddings.fail_at = 2
    async def scenario():
        await rig.indexer.run_once()
        with rig.database.session() as session:
            job = session.scalars(select(RagIndexJob)).one()
            missing_count = sum(vector is None for vector in job.vectors)
        assert len(rig.embeddings.calls) == 2
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == 2
        await rig.indexer.run_once(retry_failed=True)
        assert sum(map(len, rig.embeddings.calls[2:])) == missing_count
        assert rig.indexer.status()["counts"]["published"] == 1
    asyncio.run(scenario())


def test_qdrant_unknown_upload_resumes_from_cache_without_model_retry(rig):
    create_note(rig)
    async def scenario():
        rig.qdrant.fail_upload = True
        with pytest.raises(RagError, match="qdrant_timeout"):
            await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        with pytest.raises(RagError):
            await rig.search.search("恢复")
        rig.qdrant.fail_upload = False
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        assert rig.indexer.status()["counts"]["published"] == 1
    asyncio.run(scenario())


def test_missing_qdrant_collection_is_restored_from_sqlite_vectors(rig):
    create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        collection = rig.indexer.status()["generation"]["collection"]
        rig.qdrant.collections.pop(collection)
        with pytest.raises(RagError, match="qdrant_collection_missing"):
            await rig.search.search("恢复")
        before = len(rig.embeddings.calls)
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        assert (await rig.search.search("恢复"))["items"]
    asyncio.run(scenario())


def test_superseded_upload_cleanup_preserves_new_publication_with_identical_ids(rig):
    note = create_note(rig)
    with rig.database.session() as session:
        source = Source(title="新的关联", source_type="manual", content="原文")
        session.add(source)
        session.commit()
        source_id = source.id
    async def scenario():
        rig.qdrant.fail_upload = True
        with pytest.raises(RagError, match="qdrant_timeout"):
            await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        update_note(rig, note, source_id=source_id)
        rig.qdrant.fail_upload = False
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        result = await rig.search.search("恢复")
        assert result["items"] and result["items"][0]["source_id"] == source_id
        with rig.database.session() as session:
            assert all(job.cleanup_ids == [] for job in session.scalars(select(RagIndexJob)))
    asyncio.run(scenario())


def test_rebuild_reuses_vectors_and_clears_replaced_generation_cache(rig):
    create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        old = rig.indexer.status()["generation"]
        before = len(rig.embeddings.calls)
        await rig.indexer.run_once(rebuild=True)
        current = rig.indexer.status()["generation"]
        assert old["id"] != current["id"] and old["collection"] not in rig.qdrant.collections
        assert len(rig.embeddings.calls) == before
        with rig.database.session() as session:
            jobs = list(session.scalars(select(RagIndexJob).order_by(RagIndexJob.created_at)))
            assert jobs[0].vectors is None and jobs[-1].vectors is not None
    asyncio.run(scenario())


def test_rebuild_after_content_change_reclaims_all_old_vector_versions(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        update_note(rig, note, body="重建前已经发生正文变更")
        await rig.indexer.run_once(rebuild=True)
        with rig.database.session() as session:
            jobs = list(session.scalars(select(RagIndexJob).order_by(RagIndexJob.created_at)))
            assert jobs[0].content_hash != jobs[-1].content_hash
            assert jobs[0].vectors is None and jobs[-1].vectors is not None
        assert rig.indexer.status()["counts"]["published"] == 1
    asyncio.run(scenario())


def test_rebuild_keeps_excluded_notes_only_cache_until_restored(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        with rig.database.session() as session:
            state = session.get(SyncState, note["id"])
            state.status, state.last_error = "error", "invalid_markdown"
            session.commit()
        await rig.indexer.run_once(rebuild=True)
        with rig.database.session() as session:
            assert session.scalars(select(RagIndexJob)).one().vectors is not None
            state = session.get(SyncState, note["id"])
            state.status, state.last_error = "pending", None
            session.commit()
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        with rig.database.session() as session:
            jobs = list(session.scalars(select(RagIndexJob).order_by(RagIndexJob.created_at)))
            assert jobs[0].vectors is None and jobs[-1].vectors is not None
    asyncio.run(scenario())


def test_context_validation_refreshes_path_and_rejects_changed_content(rig):
    note = create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        items = (await rig.search.search("恢复"))["items"]
        with rig.database.session() as session:
            session.get(SyncState, note["id"]).path = "新目录/恢复.md"
            session.commit()
        assert rig.search.validate_context(items)
        assert items[0]["path"] == "新目录/恢复.md"
        update_note(rig, note, body="生成期间内容已经改变")
        assert not rig.search.validate_context(items)
    asyncio.run(scenario())


def test_source_association_update_reuses_note_vectors_and_refreshes_reference(rig):
    note = create_note(rig)
    with rig.database.session() as session:
        source = Source(source_type="manual", title="引用来源", content="不纳入向量索引")
        session.add(source)
        session.commit()
        source_id = source.id
    async def scenario():
        await rig.indexer.run_once()
        before = len(rig.embeddings.calls)
        updated = update_note(rig, note, source_id=source_id)
        await rig.indexer.run_once()
        assert len(rig.embeddings.calls) == before
        items = (await rig.search.search("恢复"))["items"]
        assert items[0]["version"] == updated["version"]
        assert items[0]["source_id"] == source_id
        assert items[0]["source"]["title"] == "引用来源"
        assert "不纳入向量索引" not in items[0]["text"]
    asyncio.run(scenario())


def test_profile_change_requires_explicit_rebuild(rig):
    create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        rig.registry.profiles["fake"] = rig.registry.profiles["fake"].model_copy(update={"model_revision": "v2"})
        with pytest.raises(RagError, match="rag_rebuild_required"):
            await rig.indexer.run_once()
        with pytest.raises(RagError, match="rag_rebuild_required"):
            await rig.search.search("恢复")
        before = len(rig.embeddings.calls)
        await rig.indexer.run_once(rebuild=True)
        assert len(rig.embeddings.calls) > before
    asyncio.run(scenario())


def test_owned_collection_mismatch_never_embeds_or_modifies(rig):
    create_note(rig)
    async def scenario():
        await rig.indexer.run_once()
        collection = rig.indexer.status()["generation"]["collection"]
        original = dict(rig.qdrant.collections[collection])
        rig.qdrant.metadata[collection] = {"owner": "someone_else"}
        before = len(rig.embeddings.calls)
        with pytest.raises(RagError, match="ownership_mismatch"):
            await rig.indexer.run_once()
        assert rig.qdrant.collections[collection] == original
        assert len(rig.embeddings.calls) == before
    asyncio.run(scenario())


def test_concurrent_note_change_cannot_publish_old_snapshot(rig):
    note = create_note(rig)
    async def hook(texts):
        await asyncio.to_thread(update_note, rig, note, body="模型调用期间已修改")
    rig.embeddings.hook = hook
    async def scenario():
        await rig.indexer.run_once()
        with pytest.raises(RagError, match="rag_index_not_ready"):
            await rig.search.search("恢复")
        assert rig.indexer.status()["counts"]["published"] == 0
        rig.embeddings.hook = None
        await rig.indexer.run_once()
        assert rig.indexer.status()["counts"]["published"] == 1
    asyncio.run(scenario())


def test_stale_upload_cleanup_is_persistent_when_point_deletion_fails(rig):
    note = create_note(rig)
    async def hook(texts):
        await asyncio.to_thread(update_note, rig, note, body="调用完成前已被更新")
    rig.embeddings.hook = hook
    rig.qdrant.fail_delete = True
    async def scenario():
        with pytest.raises(RagError, match="qdrant_delete_timeout"):
            await rig.indexer.run_once()
        with rig.database.session() as session:
            stale = session.scalars(select(RagIndexJob)).one()
            assert stale.status == "superseded" and stale.cleanup_ids
            stale_ids, stale_id = set(stale.cleanup_ids), stale.id
        rig.qdrant.fail_delete = False
        rig.embeddings.hook = None
        await rig.indexer.run_once()
        collection = rig.indexer.status()["generation"]["collection"]
        assert stale_ids.isdisjoint(rig.qdrant.collections[collection])
        with rig.database.session() as session:
            assert session.get(RagIndexJob, stale_id).cleanup_ids == []
        assert rig.indexer.status()["counts"]["published"] == 1
    asyncio.run(scenario())


def test_stop_drains_current_batch_and_starts_no_later_paid_calls(rig):
    create_note(rig, "长文正文" * 120)
    async def hook(texts):
        rig.indexer.request_stop()
    rig.embeddings.hook = hook
    async def scenario():
        await rig.indexer.run_once()
        await rig.indexer.close()
    asyncio.run(scenario())
    assert len(rig.embeddings.calls) == 1
    with rig.database.session() as session:
        job = session.scalars(select(RagIndexJob)).one()
        assert job.intents[0]["status"] == "succeeded"
        assert job.status == "pending"


def test_interrupted_call_recovery_requires_manual_retry(rig):
    create_note(rig)
    class Interrupted(BaseException):
        pass
    async def hook(texts):
        raise Interrupted()
    rig.embeddings.hook = hook
    with pytest.raises(Interrupted):
        asyncio.run(rig.indexer.run_once())
    rig.indexer.recover_interrupted()
    rig.embeddings.hook = None
    asyncio.run(rig.indexer.run_once())
    assert len(rig.embeddings.calls) == 1
    with rig.database.session() as session:
        job = session.scalars(select(RagIndexJob)).one()
        assert job.status == "interrupted" and job.intents[-1]["status"] == "outcome_unknown"
    asyncio.run(rig.indexer.run_once(retry_failed=True))
    assert len(rig.embeddings.calls) == 2


def test_sources_are_never_indexed(rig):
    with rig.database.session() as session:
        session.add(Source(title="私有原文", content="不应索引", source_type="manual"))
        session.commit()
    asyncio.run(rig.indexer.run_once())
    assert rig.embeddings.calls == []
    assert rig.indexer.status()["counts"]["published"] == 0


def test_oversize_note_is_reported_without_truncation_or_paid_call(rig):
    create_note(rig, "正文" * 100)
    rig.settings.rag_max_note_chars = 100
    asyncio.run(rig.indexer.run_once())
    status = rig.indexer.status()
    assert status["index_incomplete"] and rig.embeddings.calls == []
    assert status["errors"][0]["error_code"] == "rag_document_too_large"
