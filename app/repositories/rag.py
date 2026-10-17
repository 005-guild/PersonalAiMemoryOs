"""Short SQLite units of work for RAG snapshots and publication manifests."""

import hashlib
from uuid import UUID, uuid5

from sqlalchemy import select

from app.models.base import new_id, utcnow
from app.models.content import Knowledge, Source
from app.models.rag import RagIndexGeneration, RagIndexJob, RagNoteIndexState
from app.models.sync import SyncConflict, SyncState
from app.vector.chunking import render_note

NOTE_FIELDS = ("id", "version", "source_id", "title", "body", "summary", "category", "tags", "concepts")


def hash_note(snapshot):
    return hashlib.sha256(render_note(snapshot).encode("utf-8")).hexdigest()


def generation_dict(generation):
    if generation is None:
        return None
    return {field: getattr(generation, field) for field in (
        "id", "owner_id", "collection", "profile_id", "fingerprint", "dimension",
        "configuration", "status", "error_code", "created_at", "updated_at")}


def job_dict(job):
    return {field: getattr(job, field) for field in (
        "id", "generation_id", "knowledge_id", "version", "content_hash", "snapshot",
        "chunks", "vectors", "intents", "cleanup_ids", "status", "error_code")}


def collection_metadata(generation):
    return {"application": "personal-ai-memory-os", "generation_id": generation["id"],
            "owner_id": generation["owner_id"]}


class RagRepository:
    def __init__(self, session):
        self.session = session

    def current(self):
        return self.session.scalars(select(RagIndexGeneration).where(
            RagIndexGeneration.status.in_(["building", "ready"])
        ).order_by(RagIndexGeneration.created_at.desc())).first()

    def note(self, knowledge_id):
        note = self.session.get(Knowledge, knowledge_id)
        if note is None:
            return None, "missing"
        snapshot = {field: getattr(note, field) for field in NOTE_FIELDS}
        state = self.session.get(SyncState, note.id)
        snapshot["path"] = state.path if state else None
        source = self.session.get(Source, note.source_id) if note.source_id else None
        snapshot["source"] = ({field: getattr(source, field) for field in (
            "id", "title", "author", "url", "source_type", "version", "deleted_at")}
            if source else None)
        if note.deleted_at is not None:
            return snapshot, "deleted"
        conflict = self.session.scalars(select(SyncConflict.id).where(
            SyncConflict.knowledge_id == note.id, SyncConflict.status == "open")).first()
        if conflict is not None or (state and state.status == "conflict"):
            return snapshot, "sync_conflict"
        if state and (state.status == "error" or state.last_error):
            return snapshot, "sync_error"
        return snapshot, None

    def notes(self):
        return [self.note(identity) for identity in self.session.scalars(select(Knowledge.id))]

    def start_generation(self, resolved, fingerprint, configuration):
        for previous in self.session.scalars(select(RagIndexGeneration).where(
                RagIndexGeneration.status.in_(["building", "ready"]))):
            previous.status = "retired"
            previous.updated_at = utcnow()
        identity = new_id()
        generation = RagIndexGeneration(
            id=identity, collection="memory_os_" + identity.replace("-", ""),
            profile_id=resolved.profile_id, fingerprint=fingerprint,
            dimension=resolved.profile.dimension, configuration=configuration, status="building")
        self.session.add(generation)
        self.session.flush()
        return generation_dict(generation)

    def prepare_job(self, generation, snapshot, chunks, retry_failed):
        key = (generation["id"], snapshot["id"])
        state = self.session.get(RagNoteIndexState, key)
        digest = hash_note(snapshot)
        same = state is not None and state.version == snapshot["version"] and state.content_hash == digest
        if same and state.status == "published":
            return None
        if same and state.pending_job_id:
            previous = self.session.get(RagIndexJob, state.pending_job_id)
            if previous and (previous.version != snapshot["version"] or previous.content_hash != digest):
                previous = None
            if previous and previous.status in {"failed", "interrupted", "embedding"}:
                if not retry_failed:
                    if previous.status == "embedding":
                        self.fail_job(previous.id, "embedding_call_interrupted", "interrupted")
                    return None
                previous.status, previous.error_code = "pending", None
                state.status, state.error_code = "pending", None
                return job_dict(previous)
            if previous and previous.status in {"pending", "cached", "uploading"}:
                return job_dict(previous)
        if not retry_failed:
            interrupted = self.session.scalars(select(RagIndexJob).join(
                RagIndexGeneration, RagIndexGeneration.id == RagIndexJob.generation_id
            ).where(RagIndexJob.knowledge_id == snapshot["id"], RagIndexJob.content_hash == digest,
                    RagIndexGeneration.fingerprint == generation["fingerprint"],
                    RagIndexJob.status.in_(["failed", "interrupted", "embedding"]))).first()
            if interrupted:
                # A file move, lifecycle version, or rebuild must not silently retry an unknown paid call.
                if state is None:
                    state = RagNoteIndexState(generation_id=generation["id"], knowledge_id=snapshot["id"],
                        version=snapshot["version"], content_hash=digest, status="interrupted")
                    self.session.add(state)
                state.version, state.content_hash = snapshot["version"], digest
                state.status, state.error_code = "interrupted", "embedding_retry_required"
                return None
        vectors = [None] * len(chunks)
        # Reuse only validated vectors from an identical semantic configuration and text.
        cached = self.session.scalars(select(RagIndexJob).join(
            RagIndexGeneration, RagIndexGeneration.id == RagIndexJob.generation_id
        ).where(RagIndexJob.knowledge_id == snapshot["id"], RagIndexJob.content_hash == digest,
                RagIndexGeneration.fingerprint == generation["fingerprint"],
                RagIndexJob.vectors.is_not(None)).order_by(RagIndexJob.created_at.desc()))
        for previous in cached:
            if (len(previous.chunks) == len(chunks)
                    and all(a["text"] == b["text"] for a, b in zip(previous.chunks, chunks))):
                for index, vector in enumerate(previous.vectors or []):
                    if index < len(vectors) and vector is not None and vectors[index] is None:
                        vectors[index] = vector
        chunks = [{**chunk, "id": str(uuid5(UUID(generation["id"]),
                  f"{snapshot['id']}:{digest}:{chunk['ordinal']}"))} for chunk in chunks]
        job = RagIndexJob(generation_id=generation["id"], knowledge_id=snapshot["id"],
                          version=snapshot["version"], content_hash=digest, snapshot=snapshot,
                          chunks=chunks, vectors=vectors, status="pending")
        self.session.add(job)
        self.session.flush()
        if state is None:
            state = RagNoteIndexState(generation_id=generation["id"], knowledge_id=snapshot["id"],
                                      version=snapshot["version"], content_hash=digest, status="pending")
            self.session.add(state)
        elif state.pending_job_id:
            previous = self.session.get(RagIndexJob, state.pending_job_id)
            if previous and previous.status not in {"published", "failed", "interrupted"}:
                if previous.status in {"uploading", "superseded"}:
                    previous.cleanup_ids = [chunk["id"] for chunk in previous.chunks]
                previous.status = "superseded"
        state.version, state.content_hash = snapshot["version"], digest
        state.pending_job_id, state.status, state.error_code = job.id, "pending", None
        state.updated_at = utcnow()
        self.session.flush()
        return job_dict(job)

    def excluded(self, generation, snapshot, reason):
        key = (generation["id"], snapshot["id"])
        state = self.session.get(RagNoteIndexState, key)
        if state is None:
            state = RagNoteIndexState(generation_id=generation["id"], knowledge_id=snapshot["id"],
                                      version=snapshot["version"], content_hash=hash_note(snapshot), status="excluded")
            self.session.add(state)
        state.status, state.error_code, state.updated_at = "excluded", reason, utcnow()
        state.version, state.content_hash = snapshot["version"], hash_note(snapshot)

    def set_job(self, job_id, **values):
        job = self.session.get(RagIndexJob, job_id)
        for key, value in values.items():
            setattr(job, key, value)
        job.updated_at = utcnow()
        self.session.flush()
        return job_dict(job)

    def fail_job(self, job_id, code, status="failed"):
        job = self.session.get(RagIndexJob, job_id)
        job.status, job.error_code, job.updated_at = status, code, utcnow()
        state = self.session.get(RagNoteIndexState, (job.generation_id, job.knowledge_id))
        if state and state.pending_job_id == job.id:
            state.status, state.error_code = status, code

    def publish(self, job_id):
        job = self.session.get(RagIndexJob, job_id)
        generation = self.current()
        snapshot, reason = self.note(job.knowledge_id)
        state = self.session.get(RagNoteIndexState, (job.generation_id, job.knowledge_id))
        if (generation is None or generation.id != job.generation_id or reason or state is None
                or state.pending_job_id != job.id or snapshot["version"] != job.version
                or hash_note(snapshot) != job.content_hash):
            job.status = "superseded"
            job.cleanup_ids = [chunk["id"] for chunk in job.chunks]
            return False
        previous = self.session.get(RagIndexJob, state.published_job_id) if state.published_job_id else None
        current_ids = {chunk["id"] for chunk in job.chunks}
        job.cleanup_ids = ([chunk["id"] for chunk in previous.chunks if chunk["id"] not in current_ids]
                           if previous else [])
        if previous and previous.id != job.id:
            previous.vectors = None
            previous.status = "superseded"
        # A successful replacement owns the current cache, including after a rebuild.
        for cached in self.session.scalars(select(RagIndexJob).where(
                RagIndexJob.knowledge_id == job.knowledge_id, RagIndexJob.id != job.id)):
            cached.vectors = None
            cached_generation = self.session.get(RagIndexGeneration, cached.generation_id)
            if (cached.status in {"failed", "interrupted", "embedding"}
                    and cached.content_hash == job.content_hash
                    and cached_generation.fingerprint == generation.fingerprint):
                cached.status = "superseded"
        job.status, job.error_code = "published", None
        state.status, state.error_code = "published", None
        state.published_job_id, state.pending_job_id = job.id, None
        state.version, state.content_hash, state.updated_at = job.version, job.content_hash, utcnow()
        return True

    def valid_chunks(self, generation_id):
        valid = {}
        states = self.session.scalars(select(RagNoteIndexState).where(
            RagNoteIndexState.generation_id == generation_id,
            RagNoteIndexState.status == "published"))
        for state in states:
            snapshot, reason = self.note(state.knowledge_id)
            if reason or snapshot["version"] != state.version or hash_note(snapshot) != state.content_hash:
                continue
            job = self.session.get(RagIndexJob, state.published_job_id)
            if job is None or job.status != "published" or job.version != state.version:
                continue
            for chunk in job.chunks:
                valid[chunk["id"]] = {"chunk_id": chunk["id"], "knowledge_id": snapshot["id"],
                    "version": snapshot["version"], "title": snapshot["title"], "path": snapshot["path"],
                    "source_id": snapshot["source_id"], "source": snapshot["source"],
                    "text": chunk["text"], "content_hash": state.content_hash, "generation_id": generation_id}
        return valid
