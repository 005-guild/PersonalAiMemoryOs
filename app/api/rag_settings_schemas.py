"""Write-only credentials and explicit non-indexing configuration probes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.settings_schemas import AIKeyUpdate
from app.vector.configuration import EmbeddingProfile


class EmbeddingProfileWrite(EmbeddingProfile):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")


class RAGSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool
    qdrant_url: str = Field(min_length=1, max_length=2048)
    default_profile: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    profiles: list[EmbeddingProfileWrite] = Field(max_length=100)
    key_updates: list[AIKeyUpdate] = Field(default_factory=list, max_length=100)


class RAGSettingsTest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: Literal["qdrant", "embedding"]
    profile_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    confirm_embedding: bool = False
