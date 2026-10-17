"""Validated write contracts shared by the versioned content endpoints."""

from typing import Annotated, ClassVar
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.fields import (
    Identifier, Label, Title, MAX_BODY_LENGTH, MAX_CATEGORY_LENGTH,
    MAX_SUMMARY_LENGTH, MAX_TERM_COUNT,
)
Version = Annotated[int, Field(strict=True, ge=1)]


class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceCreate(WriteModel):
    source_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] = "manual"
    title: Title
    author: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=4096)
    content: str = Field(default="", max_length=2_000_000)


class PatchModel(WriteModel):
    expected_version: Version
    nullable_fields: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def require_changes(self):
        changes = self.model_fields_set - {"expected_version"}
        if not changes:
            raise ValueError("Include at least one field to update.")
        if any(getattr(self, field) is None and field not in self.nullable_fields for field in changes):
            raise ValueError("A required content field cannot be null.")
        return self


class SourcePatch(PatchModel):
    nullable_fields: ClassVar[set[str]] = {"author", "url"}
    source_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None = None
    title: Title | None = None
    author: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=4096)
    content: str | None = Field(default=None, max_length=2_000_000)


class SourceAssociations(WriteModel):
    source_id: Identifier | None = None
    source_ids: list[Identifier] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_associations(self):
        if "source_ids" in self.model_fields_set:
            if self.source_ids is None or len(set(self.source_ids)) != len(self.source_ids):
                raise ValueError("source_ids must be a list of unique Sources.")
            first = self.source_ids[0] if self.source_ids else None
            if "source_id" in self.model_fields_set and self.source_id != first:
                raise ValueError("source_id must equal the first source_ids entry.")
            self.source_id = first
        return self


class KnowledgeCreate(SourceAssociations):
    title: Title
    body: str = Field(default="", max_length=MAX_BODY_LENGTH)
    summary: str = Field(default="", max_length=MAX_SUMMARY_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_CATEGORY_LENGTH)
    tags: list[Label] = Field(default_factory=list, max_length=MAX_TERM_COUNT)
    concepts: list[Label] = Field(default_factory=list, max_length=MAX_TERM_COUNT)


class KnowledgePatch(PatchModel, SourceAssociations):
    nullable_fields: ClassVar[set[str]] = {"source_id", "category"}
    source_id: Identifier | None = None
    title: Title | None = None
    body: str | None = Field(default=None, max_length=MAX_BODY_LENGTH)
    summary: str | None = Field(default=None, max_length=MAX_SUMMARY_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_CATEGORY_LENGTH)
    tags: list[Label] | None = Field(default=None, max_length=MAX_TERM_COUNT)
    concepts: list[Label] | None = Field(default=None, max_length=MAX_TERM_COUNT)


class RestoreRequest(WriteModel):
    expected_version: Version


class KnowledgeRestore(RestoreRequest, SourceAssociations):
    pass


class RecordRead(BaseModel):
    id: str
    version: int
    created_at: str
    updated_at: str
    deleted_at: str | None


class SourceRead(RecordRead):
    source_type: str
    title: str
    author: str | None
    url: str | None
    content: str


class KnowledgeRead(RecordRead):
    source_id: str | None
    source_ids: list[str] = Field(default_factory=list)
    title: str
    body: str
    summary: str
    category: str | None
    tags: list[str]
    concepts: list[str]
    deleted: bool
    sync_status: str


class SourcePage(BaseModel):
    items: list[SourceRead]
    total: int
    offset: int
    limit: int


class KnowledgePage(BaseModel):
    items: list[KnowledgeRead]
    total: int
    offset: int
    limit: int
