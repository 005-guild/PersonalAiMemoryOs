"""Editable trusted instructions are business resources, not secret settings."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.processing import _errors
from app.api.schemas import Version

router = APIRouter(prefix="/api/v1/prompt-templates", tags=["prompt templates"])


class PromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    content: str = Field(min_length=1, max_length=100000)
    output_schema_version: Literal[1, 2] = 2

    @field_validator("output_schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value):
        if type(value) is not int:
            raise ValueError("Output schema must be integer 1 or 2.")
        return value

    @model_validator(mode="after")
    def visible(self):
        if not self.name.strip() or not self.content.strip():
            raise ValueError("Name and content must not be blank.")
        for value in (self.name, self.description, self.content):
            value.encode("utf-8")
        return self


class PromptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: Version
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    content: str | None = Field(default=None, min_length=1, max_length=100000)
    output_schema_version: Literal[1, 2] | None = None

    @field_validator("output_schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("Output schema must be integer 1 or 2.")
        return value

    @model_validator(mode="after")
    def changes(self):
        values = self.model_dump(exclude_unset=True, exclude={"expected_version"})
        if not values or any(value is None for value in values.values()):
            raise ValueError("Include non-null prompt changes.")
        for key in ("name", "content"):
            if key in values and not values[key].strip():
                raise ValueError("Prompt fields must not be blank.")
        for value in values.values():
            if isinstance(value, str):
                value.encode("utf-8")
        return self


class PromptAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Version


@router.get("")
def list_templates(request: Request, include_archived: bool = False,
                   offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with _errors():
        return request.app.state.processing.templates.list(include_archived=include_archived, offset=offset, limit=limit)


@router.post("", status_code=201)
def create_template(payload: PromptCreate, request: Request):
    with _errors():
        return request.app.state.processing.templates.create(payload.model_dump())


@router.get("/{identifier}")
def get_template(identifier: UUID, request: Request):
    with _errors():
        return request.app.state.processing.templates.get(str(identifier))


@router.patch("/{identifier}")
def edit_template(identifier: UUID, payload: PromptPatch, request: Request):
    with _errors():
        return request.app.state.processing.templates.change(str(identifier), payload.expected_version,
            payload.model_dump(exclude_unset=True, exclude={"expected_version"}))


@router.post("/{identifier}/default")
def default_template(identifier: UUID, payload: PromptAction, request: Request):
    with _errors():
        return request.app.state.processing.templates.change(str(identifier), payload.expected_version, action="default")


@router.post("/{identifier}/archive")
def archive_template(identifier: UUID, payload: PromptAction, request: Request):
    with _errors():
        return request.app.state.processing.templates.change(str(identifier), payload.expected_version, action="archive")


@router.get("/{identifier}/revisions")
def revisions(identifier: UUID, request: Request):
    with _errors():
        return request.app.state.processing.templates.revisions(str(identifier))
