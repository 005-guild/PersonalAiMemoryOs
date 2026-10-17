"""Small synchronization projections for polling and paged issue inspection."""

from sqlalchemy import func, select

from app.models import SyncState


def summary(sync):
    with sync.lock, sync.database.session() as session:
        counts = dict(session.execute(select(SyncState.status, func.count()).group_by(SyncState.status)).all())
        return {"enabled": sync.settings.sync_enabled, "running": sync.worker_running,
                "last_scan_at": sync.last_scan_at, "last_error": sync.last_error,
                "counts": counts, "issue_count": len(sync.issues), "note_count": sum(counts.values())}


def notes(sync, *, offset=0, limit=20, status=None):
    with sync.lock, sync.database.session() as session:
        where = [SyncState.status == status] if status is not None else []
        total = session.scalar(select(func.count()).select_from(SyncState).where(*where)) or 0
        rows = session.execute(select(*(getattr(SyncState, key) for key in (
            "knowledge_id", "path", "status", "last_error", "last_synced_at")))
            .where(*where).order_by(SyncState.knowledge_id).offset(offset).limit(limit)).mappings()
        return {"items": [dict(row) for row in rows], "total": int(total), "offset": offset, "limit": limit}


def issues(sync, *, offset=0, limit=20):
    with sync.lock:
        return {"items": list(sync.issues[offset:offset + limit]), "total": len(sync.issues),
                "offset": offset, "limit": limit, "last_scan_at": sync.last_scan_at}
