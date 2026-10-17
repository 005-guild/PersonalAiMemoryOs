"""HTTP contracts for configured AI profiles and immutable generated drafts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.schemas import KnowledgeRead, Version
from app.models.fields import Identifier
from app.services.processing_output import KnowledgeOutput
from app.services.processing_v2 import KnowledgeOutputV2

ProfileID = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
RunStatus = Literal["running", "ready", "failed", "interrupted", "adopted"]


class ProcessingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: Identifier
    expected_source_version: Version
    profile_id: ProfileID | None = None
    prompt_template_id: Identifier | None = None
    prompt_template_version: int | None = Field(default=None, strict=True, ge=1)
    generation_settings: "GenerationSettings | None" = None


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_output_tokens: int = Field(default=16384, ge=1, le=131072)
    timeout_seconds: float = Field(default=180.0, ge=0.01, le=600)


class AdoptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Version


class RunSummary(BaseModel):
    id: str
    version: int
    source_id: str
    source_version: int
    source_count: int = 1
    source_ids: list[str] = Field(default_factory=list)
    profile_id: str
    protocol: str
    model: str
    status: RunStatus
    source_stale: bool
    error_code: str | None = None
    adopted_knowledge_id: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class RunRead(RunSummary):
    source_snapshot: dict
    input_hash: str
    config_fingerprint: str
    prompt_version: str
    prompt_hash: str
    output_schema_version: int
    result: KnowledgeOutputV2 | KnowledgeOutput | None = None
    proposal: dict | None = None
    usage: dict[str, int | None] | None = None
    source_snapshots: list[dict] = Field(default_factory=list)
    prompt_snapshot: dict | None = None
    generation_settings: dict | None = None
    finish_reason: str | None = None
    failure_stage: str | None = None


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int
    offset: int
    limit: int


class AdoptRead(BaseModel):
    run: RunRead
    knowledge: KnowledgeRead
    already_adopted: bool


class ProfileRead(BaseModel):
    id: str
    label: str
    protocol: str
    model: str
    enabled: bool
    configured: bool


class ProfilesRead(BaseModel):
    enabled: bool
    max_input_chars: int = 20000
    default_profile: str | None
    items: list[ProfileRead]
    error_code: str | None = None
