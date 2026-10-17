"""SQL-only RAG status metadata; polling never loads note bodies or vector caches."""

from sqlalchemy import and_, case, func, select

from app.models import Knowledge, SyncConflict, SyncState
from app.models.rag import RagIndexJob, RagNoteIndexState
from app.repositories.rag import generation_dict


def note_projection():
    conflict = select(1).where(SyncConflict.knowledge_id == Knowledge.id,
                               SyncConflict.status == "open").exists()
    reason = case((Knowledge.deleted_at.is_not(None), "deleted"),
                  ((conflict | (SyncState.status == "conflict")), "sync_conflict"),
                  (((SyncState.status == "error") | and_(SyncState.last_error.is_not(None), SyncState.last_error != "")), "sync_error"), else_=None)
    return select(Knowledge.id.label("knowledge_id"), Knowledge.version, Knowledge.title,
                  reason.label("reason")).outerjoin(SyncState, SyncState.knowledge_id == Knowledge.id).subquery()


def status(index, repository):
    session = repository.session
    generation = generation_dict(repository.current())
    notes = note_projection()
    eligible = notes.c.reason.is_(None)
    counts = session.execute(select(
        func.coalesce(func.sum(case((eligible, 1), else_=0)), 0),
        func.coalesce(func.sum(case((notes.c.reason.is_not(None), 1), else_=0)), 0),
        func.coalesce(func.sum(case((and_(notes.c.reason.is_not(None), notes.c.reason != "deleted"), 1), else_=0)), 0),
    ).select_from(notes)).one()
    published = failed = errors = 0
    if generation:
        states = RagNoteIndexState
        query = select(
            func.coalesce(func.sum(case((and_(eligible, states.version == notes.c.version, states.status == "published",
                RagIndexJob.status == "published", RagIndexJob.version == notes.c.version,
                RagIndexJob.generation_id == generation["id"], RagIndexJob.knowledge_id == notes.c.knowledge_id,
                RagIndexJob.content_hash == states.content_hash), 1), else_=0)), 0),
            func.coalesce(func.sum(case((and_(eligible, states.version == notes.c.version,
                states.status.in_(["failed", "interrupted"])), 1), else_=0)), 0))
        published, failed = session.execute(query.select_from(notes).outerjoin(states, and_(
            states.knowledge_id == notes.c.knowledge_id, states.generation_id == generation["id"]))
            .outerjoin(RagIndexJob, RagIndexJob.id == states.published_job_id)).one()
        errors = session.scalar(select(func.count()).select_from(states).where(
            states.generation_id == generation["id"], states.error_code.is_not(None))) or 0
    eligible_count, excluded_count, blocked_count = map(int, counts)
    return {"enabled": index.settings.rag_enabled, "running": index.running,
            "worker_running": index.worker_running, "last_scan_at": index.last_scan_at,
            "last_error": index.last_error or (generation["error_code"] if generation else None),
            "generation": generation, "counts": {"published": int(published),
                "pending": max(0, eligible_count - published - failed), "failed": int(failed), "excluded": excluded_count},
            "index_incomplete": generation is None or bool(blocked_count) or published != eligible_count,
            "error_count": int(errors)}


def details(repository, kind, *, offset=0, limit=20):
    session = repository.session
    generation = repository.current()
    if kind == "errors":
        state = RagNoteIndexState
        query = select(state.knowledge_id, state.status, state.error_code)
        where = [state.generation_id == generation.id, state.error_code.is_not(None)] if generation else [False]
        query = query.where(*where)
        ordering = state.knowledge_id
    else:
        notes = note_projection()
        query = select(notes.c.knowledge_id, notes.c.title, notes.c.reason).where(notes.c.reason.is_not(None))
        ordering = notes.c.knowledge_id
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(query.order_by(ordering).offset(offset).limit(limit)).mappings()
    return {"items": [dict(row) for row in rows], "total": int(total), "offset": offset, "limit": limit,
            "generation_id": generation.id if generation else None}
