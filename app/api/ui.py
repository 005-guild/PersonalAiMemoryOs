"""Read-only, lightweight browser views; business writes use existing APIs."""

from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Query, Request

from app.api.dependencies import request_session
from app.api.ui_schemas import UIKnowledgePage, UIOverview, UISourceGroupPage, UISourcePage
from app.repositories.ui import RecordState, SortOrder, SourceGroupSort
from app.services.ui import UIService

router = APIRouter(prefix="/api/v1/ui", tags=["workbench"])


@router.get("/drafts")
def drafts(request: Request, q: str = Query("", max_length=500),
           state: Literal["ready", "adopted", "all"] = "all", profile_id: str | None = None,
           source_id: UUID | None = None, prompt_template_id: UUID | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return UIService(session).drafts(q=q, state=state, profile_id=profile_id,
            source_id=str(source_id) if source_id else None,
            prompt_template_id=str(prompt_template_id) if prompt_template_id else None, offset=offset, limit=limit)


@router.get("/overview", response_model=UIOverview)
def overview(request: Request) -> dict:
    with request_session(request) as session:
        return UIService(session).overview()


@router.get("/sources", response_model=UISourcePage)
def sources(request: Request, q: str = Query(default="", max_length=500),
            state: RecordState = "active", offset: int = Query(default=0, ge=0),
            limit: int = Query(default=20, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return UIService(session).sources(q=q, state=state, offset=offset, limit=limit)


@router.get("/knowledge", response_model=UIKnowledgePage)
def knowledge(request: Request, q: str = Query(default="", max_length=500),
              state: RecordState = "active", source_id: UUID | None = None,
              offset: int = Query(default=0, ge=0),
              limit: int = Query(default=20, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return UIService(session).knowledge(
            q=q, state=state, offset=offset, limit=limit,
            source_id=str(source_id) if source_id is not None else None,
        )


@router.get("/source-groups", response_model=UISourceGroupPage)
def source_groups(request: Request, q: str = Query(default="", max_length=500),
                  state: RecordState = "active", offset: int = Query(default=0, ge=0),
                  limit: int = Query(default=20, ge=1, le=100),
                  sort_by: SourceGroupSort = "updated_at", order: SortOrder = "desc") -> dict:
    with request_session(request) as session:
        return UIService(session).source_groups(
            q=q, state=state, offset=offset, limit=limit, sort_by=sort_by, order=order,
        )


@router.get("/source-groups/items", response_model=UISourcePage)
def source_group_items(request: Request, title: str = Query(min_length=1, max_length=500),
                       state: RecordState = "active", offset: int = Query(default=0, ge=0),
                       limit: int = Query(default=5, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return UIService(session).source_group_items(title=title, state=state, offset=offset, limit=limit)
