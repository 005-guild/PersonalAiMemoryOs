"""Source and Knowledge APIs; synchronizer owns all Markdown file writes."""

from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.dependencies import request_session
from app.api.schemas import (
    KnowledgeCreate, KnowledgePage, KnowledgePatch, KnowledgeRead, KnowledgeRestore,
    RestoreRequest, SourceCreate, SourcePage, SourcePatch, SourceRead,
)
from app.services.content import ContentService

router = APIRouter(prefix="/api/v1", tags=["content"])


@router.post("/sources", status_code=201, response_model=SourceRead)
def create_source(payload: SourceCreate, request: Request) -> dict:
    with request_session(request) as session:
        return ContentService(session).create_source(payload.model_dump())


@router.get("/sources", response_model=SourcePage)
def list_sources(request: Request, include_deleted: bool = False,
                 offset: int = Query(default=0, ge=0),
                 limit: int = Query(default=20, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return ContentService(session).list_sources(
            include_deleted=include_deleted, offset=offset, limit=limit
        )


@router.get("/sources/{source_id}", response_model=SourceRead)
def get_source(source_id: UUID, request: Request, include_deleted: bool = False) -> dict:
    with request_session(request) as session:
        service = ContentService(session)
        return service.source_dict(service.source(str(source_id), include_deleted=include_deleted))


@router.patch("/sources/{source_id}", response_model=SourceRead)
def patch_source(source_id: UUID, payload: SourcePatch, request: Request) -> dict:
    values = payload.model_dump(exclude_unset=True)
    expected_version = values.pop("expected_version")
    with request_session(request) as session:
        return ContentService(session).update_source(str(source_id), expected_version, values)


@router.delete("/sources/{source_id}", response_model=SourceRead)
def delete_source(source_id: UUID, request: Request, expected_version: int = Query(ge=1)) -> dict:
    with request_session(request) as session:
        return ContentService(session).delete_source(str(source_id), expected_version)


@router.post("/sources/{source_id}/restore", response_model=SourceRead)
def restore_source(source_id: UUID, payload: RestoreRequest, request: Request) -> dict:
    with request_session(request) as session:
        return ContentService(session).restore_source(str(source_id), payload.expected_version)


@router.post("/knowledge", status_code=201, response_model=KnowledgeRead)
def create_knowledge(payload: KnowledgeCreate, request: Request) -> dict:
    with request_session(request) as session:
        return ContentService(session).create_knowledge(payload.model_dump())


@router.get("/knowledge", response_model=KnowledgePage)
def list_knowledge(request: Request, include_deleted: bool = False, source_id: UUID | None = None,
                   offset: int = Query(default=0, ge=0),
                   limit: int = Query(default=20, ge=1, le=100)) -> dict:
    with request_session(request) as session:
        return ContentService(session).list_knowledge(
            include_deleted=include_deleted, offset=offset, limit=limit,
            source_id=str(source_id) if source_id is not None else None,
        )


@router.get("/knowledge/{knowledge_id}", response_model=KnowledgeRead)
def get_knowledge(knowledge_id: UUID, request: Request, include_deleted: bool = False) -> dict:
    with request_session(request) as session:
        service = ContentService(session)
        return service.knowledge_dict(
            service.knowledge(str(knowledge_id), include_deleted=include_deleted)
        )


@router.patch("/knowledge/{knowledge_id}", response_model=KnowledgeRead)
def patch_knowledge(knowledge_id: UUID, payload: KnowledgePatch, request: Request) -> dict:
    values = payload.model_dump(exclude_unset=True)
    expected_version = values.pop("expected_version")
    with request_session(request) as session:
        return ContentService(session).update_knowledge(str(knowledge_id), expected_version, values)


@router.delete("/knowledge/{knowledge_id}", response_model=KnowledgeRead)
def delete_knowledge(knowledge_id: UUID, request: Request,
                     expected_version: int = Query(ge=1)) -> dict:
    with request_session(request) as session:
        return ContentService(session).delete_knowledge(str(knowledge_id), expected_version)


@router.post("/knowledge/{knowledge_id}/restore", response_model=KnowledgeRead)
def restore_knowledge(knowledge_id: UUID, payload: KnowledgeRestore, request: Request) -> dict:
    values = payload.model_dump(exclude_unset=True)
    expected_version = values.pop("expected_version")
    with request_session(request) as session:
        return ContentService(session).restore_knowledge(str(knowledge_id), expected_version, values)
