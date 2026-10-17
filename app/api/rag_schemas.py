"""Public request and response types for semantic search and cited answers."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.api.processing_schemas import ProfileID
from app.models.fields import Identifier

QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    retry_failed: bool = False


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: QueryText
    top_k: int = Field(default=5, ge=1, le=10)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: QueryText
    top_k: int = Field(default=5, ge=1, le=10)
    profile_id: ProfileID | None = None
    prompt_template_id: Identifier | None = None
    prompt_template_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def template_pair(self):
        if self.prompt_template_version is not None and self.prompt_template_id is None:
            raise ValueError("Select the prompt ID with its version.")
        return self


class SearchHit(BaseModel):
    chunk_id: str
    knowledge_id: str
    version: int
    title: str
    path: str | None = None
    source_id: str | None = None
    source: dict | None = None
    source_ids: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    text: str
    score: float
    content_hash: str
    generation_id: str


class SearchRead(BaseModel):
    items: list[SearchHit]
    index_incomplete: bool


class AnswerRead(BaseModel):
    insufficient_evidence: bool
    answer: str
    paragraphs: list[dict]
    citations: list[dict]
    index_incomplete: bool
    profile_id: str
    model: str
    usage: dict
    prompt_version: str
    prompt_hash: str
    prompt_template: dict | None = None
