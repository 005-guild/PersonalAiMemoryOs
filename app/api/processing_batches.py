"""Persistent batch submission and explicit resume/retry/cancellation."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.processing import _errors
from app.api.processing_schemas import GenerationSettings, ProfileID
from app.api.schemas import Version
from app.models.fields import Identifier

router = APIRouter(prefix="/api/v1/processing/batches", tags=["processing batches"])


class BatchSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: Identifier
    expected_version: Version


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    client_request_id: str = Field(min_length=1, max_length=100)
    mode: Literal["individual", "merged"]
    sources: list[BatchSource] = Field(min_length=1, max_length=20)
    profile_id: ProfileID | None = None
    prompt_template_id: Identifier | None = None
    prompt_template_version: int | None = Field(default=None, strict=True, ge=1)
    generation_settings: GenerationSettings = Field(default_factory=GenerationSettings)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Selected sources must be unique.")
        if not self.client_request_id.strip() or any(ord(char) < 32 for char in self.client_request_id):
            raise ValueError("Invalid client_request_id.")
        self.client_request_id.encode("utf-8")
        if self.prompt_template_version is not None and self.prompt_template_id is None:
            raise ValueError("Specify the prompt ID with its revision.")
        return self


class BatchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Version


@router.post("", status_code=202)
async def create_batch(payload: BatchCreate, request: Request):
    with _errors():
        return await request.app.state.processing.batches.create(payload.model_dump())


@router.get("")
def list_batches(request: Request, status: Literal["pending", "running", "paused", "completed", "cancelling", "cancelled"] | None = None,
                 offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with _errors():
        return request.app.state.processing.batches.list(status=status, offset=offset, limit=limit)


@router.get("/{identifier}")
def get_batch(identifier: UUID, request: Request):
    with _errors():
        return request.app.state.processing.batches.get(str(identifier))


@router.post("/{identifier}/continue")
async def continue_batch(identifier: UUID, payload: BatchAction, request: Request):
    with _errors():
        return await request.app.state.processing.batches.action(str(identifier), payload.expected_version, "continue")


@router.post("/{identifier}/retry-failed")
async def retry_failed(identifier: UUID, payload: BatchAction, request: Request):
    with _errors():
        return await request.app.state.processing.batches.action(str(identifier), payload.expected_version, "retry-failed")


@router.post("/{identifier}/cancel")
async def cancel_batch(identifier: UUID, payload: BatchAction, request: Request):
    with _errors():
        return await request.app.state.processing.batches.action(str(identifier), payload.expected_version, "cancel")
