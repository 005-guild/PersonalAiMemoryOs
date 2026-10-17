"""Single-source generation and explicit adoption; no filesystem writes here."""

from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.agents.errors import AIError
from app.api.processing_schemas import (
    AdoptRead, AdoptRequest, ProcessingRequest, ProfilesRead, RunPage, RunRead, RunStatus,
)
from app.services.content import ContentError
from app.services.processing import ProcessingFailure

router = APIRouter(prefix="/api/v1", tags=["AI processing"])


@contextmanager
def _errors():
    try:
        yield
    except ProcessingFailure as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "run_id": exc.run_id}) from None
    except AIError as exc:
        raise HTTPException(exc.status_code, {"code": exc.code}) from None
    except ContentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(503, {"code": "database_unavailable"}) from None


@router.get("/ai/profiles", response_model=ProfilesRead)
def list_profiles(request: Request):
    return request.app.state.ai_registry.describe()


@router.post("/processing/runs", status_code=201, response_model=RunRead,
             responses={409: {"description": "Disabled profile or stale/deleted Source"},
                        429: {"description": "Another model call is running"},
                        502: {"description": "Model or generated-output failure; includes run ID"},
                        503: {"description": "AI configuration or database unavailable"},
                        504: {"description": "Model deadline exceeded; includes run ID"}})
async def generate(payload: ProcessingRequest, request: Request):
    with _errors():
        return await request.app.state.processing.generate(
            payload.source_id, payload.expected_source_version, payload.profile_id,
            prompt_template_id=payload.prompt_template_id, prompt_template_version=payload.prompt_template_version,
            generation_settings=payload.generation_settings.model_dump() if payload.generation_settings is not None else None,
        )


@router.get("/processing/runs", response_model=RunPage)
def list_runs(request: Request, source_id: UUID | None = None,
              status: RunStatus | None = None, profile_id: str | None = None,
              offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with _errors():
        return request.app.state.processing.list_runs(
            source_id=str(source_id) if source_id else None, status=status,
            profile_id=profile_id, offset=offset, limit=limit,
        )


@router.get("/processing/runs/{run_id}", response_model=RunRead)
def get_run(run_id: UUID, request: Request):
    with _errors():
        return request.app.state.processing.get_run(str(run_id))


@router.post("/processing/runs/{run_id}/adopt", status_code=201, response_model=AdoptRead)
def adopt(run_id: UUID, payload: AdoptRequest, request: Request, response: Response):
    with _errors():
        result = request.app.state.processing.adopt(str(run_id), payload.expected_version)
    response.status_code = 200 if result["already_adopted"] else 201
    return result
