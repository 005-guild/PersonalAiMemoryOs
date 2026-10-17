"""Synchronization inspection, retries and snapshot-bound conflict resolution."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.models import SyncConflict
from app.services.content import ContentError
from app.services.sync_conflicts import ConflictResolver, conflict_dict
from app.services import sync_views

router = APIRouter(prefix="/api/v1/sync", tags=["synchronization"])


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: Literal["database", "markdown"]


@router.get("/status")
def sync_status(request: Request, summary_only: bool = False) -> dict:
    sync = request.app.state.synchronizer
    return sync_views.summary(sync) if summary_only else sync.status()


@router.get("/notes")
def list_notes(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
               status: str | None = Query(None, max_length=30)):
    return sync_views.notes(request.app.state.synchronizer, offset=offset, limit=limit, status=status)


@router.get("/issues")
def list_issues(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return sync_views.issues(request.app.state.synchronizer, offset=offset, limit=limit)


@router.post("/run")
def run_sync(request: Request) -> dict:
    return request.app.state.synchronizer.run_once()


@router.get("/conflicts")
def list_conflicts(request: Request,
                   status: Literal["open", "resolved", "superseded", "all"] = "open",
                   offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                   summary_only: bool = False) -> dict:
    with request.app.state.sync_lock, request.app.state.database.session() as session:
        predicates = [] if status == "all" else [SyncConflict.status == status]
        total = session.scalar(select(func.count()).select_from(SyncConflict).where(*predicates))
        if summary_only:
            rows = session.execute(select(*(getattr(SyncConflict, key) for key in (
                "id", "knowledge_id", "status", "reason", "db_version", "file_path", "created_at", "resolved_at")))
                .where(*predicates).order_by(SyncConflict.created_at, SyncConflict.id).offset(offset).limit(limit)).mappings()
            items = [dict(row) for row in rows]
        else:
            records = session.scalars(select(SyncConflict).where(*predicates).order_by(
                SyncConflict.created_at, SyncConflict.id).offset(offset).limit(limit))
            items = [conflict_dict(record) for record in records]
        return {"items": items,
                "total": total, "offset": offset, "limit": limit}


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: UUID, request: Request) -> dict:
    with request.app.state.sync_lock, request.app.state.database.session() as session:
        conflict = session.get(SyncConflict, str(conflict_id))
        if conflict is None:
            raise HTTPException(404, "Conflict not found.")
        return conflict_dict(conflict)


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: UUID, payload: ResolveRequest, request: Request) -> dict:
    try:
        return ConflictResolver(request.app.state.synchronizer).resolve(
            str(conflict_id), payload.choice)
    except ContentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except (OSError, RuntimeError):
        raise HTTPException(503, "Knowledge files are temporarily unavailable.") from None
