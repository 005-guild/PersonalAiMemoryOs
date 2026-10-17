"""Single-owner reconciliation of committed notes into a versioned vector index."""

import asyncio
import hashlib
import json
import logging

from sqlalchemy import select

from app.models.base import utcnow
from app.models.rag import RagIndexGeneration, RagIndexJob, RagNoteIndexState
from app.repositories.rag import RagRepository, collection_metadata, generation_dict, hash_note
from app.services.rag_index_jobs import RagJobRunner
from app.vector.chunking import CHUNKER_VERSION, render_note, split_document
from app.vector.errors import RagError

logger = logging.getLogger(__name__)


class RagIndexService:
    def __init__(self, database, lock, settings, registry, embedding_client, qdrant_client):
        self.database, self.lock, self.settings = database, lock, settings
        self.registry, self.embedding_client, self.qdrant_client = registry, embedding_client, qdrant_client
        self.worker_running, self.running, self.last_error, self.last_scan_at = False, False, None, None
        self._operation_lock = asyncio.Lock()
        self._tasks, self._closing = set(), False
        self._runner = RagJobRunner(self)

    def transaction(self, operation, *args, **kwargs):
        """Only SQLite work holds the same lock used by API and Markdown changes."""
        with self.lock, self.database.session() as session:
            result = operation(RagRepository(session), *args, **kwargs)
            session.commit()
            return result

    async def db(self, operation, *args, **kwargs):
        return await asyncio.to_thread(self.transaction, operation, *args, **kwargs)

    def configuration(self, resolved):
        value = {"embedding_fingerprint": resolved.fingerprint, "chunker_version": CHUNKER_VERSION,
                 "chunk_chars": self.settings.rag_chunk_chars, "chunk_overlap": self.settings.rag_chunk_overlap,
                 "max_note_chars": self.settings.rag_max_note_chars, "max_chunks": self.settings.rag_max_chunks}
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return digest, value

    def _status(self, repository):
        generation = generation_dict(repository.current())
        notes = repository.notes()
        chunks = repository.valid_chunks(generation["id"]) if generation else {}
        published = {chunk["knowledge_id"] for chunk in chunks.values()}
        eligible = {note["id"]: note for note, reason in notes if reason is None}
        failed, problems = set(), []
        if generation:
            for state in repository.session.scalars(select(RagNoteIndexState).where(
                    RagNoteIndexState.generation_id == generation["id"])):
                current = eligible.get(state.knowledge_id)
                if (current and state.status in {"failed", "interrupted"}
                        and state.version == current["version"] and state.content_hash == hash_note(current)):
                    failed.add(state.knowledge_id)
                if state.error_code:
                    problems.append({"knowledge_id": state.knowledge_id, "status": state.status,
                                     "error_code": state.error_code})
        excluded = [{"knowledge_id": note["id"], "reason": reason} for note, reason in notes if reason]
        blocked_active = any(item["reason"] != "deleted" for item in excluded)
        return {"enabled": self.settings.rag_enabled, "running": self.running,
                "worker_running": self.worker_running, "last_scan_at": self.last_scan_at,
                "last_error": self.last_error or (generation["error_code"] if generation else None),
                "generation": generation, "counts": {"published": len(published),
                    "pending": len(set(eligible) - published - failed), "failed": len(failed), "excluded": len(excluded)},
                "index_incomplete": generation is None or blocked_active or len(published) != len(eligible),
                "errors": problems, "excluded": excluded}

    def status(self):
        return self.transaction(self._status)

    def recover_interrupted(self):
        def recover(repository):
            for job in repository.session.scalars(select(RagIndexJob).where(RagIndexJob.status == "embedding")):
                repository.fail_job(job.id, "embedding_call_interrupted", "interrupted")
                intents = list(job.intents)
                if intents and intents[-1].get("status") == "calling":
                    intents[-1] = {**intents[-1], "status": "outcome_unknown"}
                    job.intents = intents
        self.transaction(recover)

    async def request_run(self, retry_failed=False, rebuild=False):
        if self._closing:
            raise RagError(503, "rag_stopping")
        self.registry.resolve()
        if self.running or any(not task.done() for task in self._tasks):
            raise RagError(429, "rag_index_busy")
        task = asyncio.create_task(self._background_run(retry_failed, rebuild))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"status": "queued", "retry_failed": retry_failed, "rebuild": rebuild}

    async def _background_run(self, retry_failed, rebuild):
        try:
            await self.run_once(retry_failed=retry_failed, rebuild=rebuild)
        except Exception as exc:
            self.last_error = exc.code if isinstance(exc, RagError) else "rag_index_failed"
            logger.error("RAG reconciliation failed (%s).", self.last_error)

    async def run_once(self, retry_failed=False, rebuild=False):
        if self._closing or not self.settings.rag_enabled:
            return await self.db(self._status)
        async with self._operation_lock:
            if self._closing:
                return await self.db(self._status)
            self.running = True
            generation = None
            try:
                resolved = self.registry.resolve()
                fingerprint, configuration = self.configuration(resolved)
                generation = await self.db(lambda repo: generation_dict(repo.current()))
                if generation and generation["fingerprint"] != fingerprint and not rebuild:
                    raise RagError(409, "rag_rebuild_required")
                if generation is None or rebuild:
                    generation = await self.db(lambda repo: repo.start_generation(resolved, fingerprint, configuration))
                try:
                    await self.qdrant_client.ensure_collection(generation["collection"], generation["dimension"],
                        collection_metadata(generation), create=False)
                except RagError as exc:
                    if exc.code != "qdrant_collection_missing":
                        raise
                    await self.qdrant_client.ensure_collection(generation["collection"], generation["dimension"],
                        collection_metadata(generation), create=True)
                    await self.db(lambda repo: self._restore_cached_publications(repo, generation))
                # Durable cached uploads and point cleanup never repeat model calls.
                await self._runner.cleanup(generation)
                notes = await self.db(lambda repo: repo.notes())
                for snapshot, reason in notes:
                    if self._closing:
                        break
                    if reason:
                        await self.db(lambda repo, s=snapshot, r=reason: repo.excluded(generation, s, r))
                        await self._runner.remove_excluded(generation, snapshot["id"])
                        continue
                    try:
                        chunks = split_document(render_note(snapshot), self.settings.rag_chunk_chars,
                            self.settings.rag_chunk_overlap, self.settings.rag_max_note_chars, self.settings.rag_max_chunks)
                    except RagError as exc:
                        await self.db(lambda repo, s=snapshot, c=exc.code: repo.excluded(generation, s, c))
                        await self._runner.remove_excluded(generation, snapshot["id"])
                        continue
                    job = await self.db(lambda repo, s=snapshot, c=chunks:
                        repo.prepare_job(generation, s, c, retry_failed))
                    if job is not None:
                        await self._runner.process(generation, resolved, job)
                await self.db(lambda repo: self._finish_generation(repo, generation))
                self.last_error = None
                await self._runner.cleanup_retired()
            except Exception as exc:
                code = exc.code if isinstance(exc, RagError) else "rag_index_failed"
                self.last_error = code
                if generation is not None:
                    await self.db(lambda repo: self._generation_error(repo, generation["id"], code))
                raise
            finally:
                self.running, self.last_scan_at = False, utcnow()
            return await self.db(self._status)

    @staticmethod
    def _restore_cached_publications(repository, generation):
        for state in repository.session.scalars(select(RagNoteIndexState).where(
                RagNoteIndexState.generation_id == generation["id"], RagNoteIndexState.status == "published")):
            job = repository.session.get(RagIndexJob, state.published_job_id)
            if job and job.vectors and all(vector is not None for vector in job.vectors):
                job.status = "cached"
                state.status, state.pending_job_id = "pending", job.id

    @staticmethod
    def _finish_generation(repository, generation):
        record = repository.session.get(RagIndexGeneration, generation["id"])
        record.status, record.error_code, record.updated_at = "ready", None, utcnow()

    @staticmethod
    def _generation_error(repository, generation_id, code):
        record = repository.session.get(RagIndexGeneration, generation_id)
        record.error_code, record.updated_at = code, utcnow()

    def checked_snapshot(self):
        resolved = self.registry.resolve()
        fingerprint, _ = self.configuration(resolved)
        def snapshot(repository):
            current = generation_dict(repository.current())
            if current is None:
                raise RagError(503, "rag_index_missing")
            if current["fingerprint"] != fingerprint:
                raise RagError(409, "rag_rebuild_required")
            if current["status"] != "ready":
                raise RagError(503, "rag_index_building")
            if current["error_code"]:
                raise RagError(503, "rag_index_unavailable")
            return current, resolved, repository.valid_chunks(current["id"]), self._status(repository)
        return self.transaction(snapshot)

    async def search_snapshot(self):
        return await asyncio.to_thread(self.checked_snapshot)

    def request_stop(self):
        """Finish the current remote batch, but begin no more work during shutdown."""
        self._closing = True

    async def close(self):
        self.request_stop()
        tasks = list(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._operation_lock:
            pass
