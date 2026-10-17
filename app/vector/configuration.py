"""Embedding profiles separate endpoint semantics from environment credentials."""

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
import yaml

from app.config import Settings
from app.vector.errors import RagError

_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_RESERVED = {"model", "input", "encodingformat", "dimensions", "stream", "headers",
             "apikey", "authorization", "authentication", "auth", "token", "credentials",
             "accesstoken", "bearertoken"}


def _validate_extra(value: Any, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("Embedding extensions are too deeply nested.")
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str) or re.sub(r"[^a-z0-9]", "", key.lower()) in _RESERVED:
                raise ValueError("Embedding extensions cannot override protected fields.")
            _validate_extra(nested, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_extra(item, depth + 1)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("Embedding extensions must be JSON values.")


class EmbeddingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    label: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool = True
    protocol: Literal["openai_embeddings"] = "openai_embeddings"
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    model_revision: str | None = Field(default=None, min_length=1, max_length=200)
    dimension: int = Field(ge=1, le=65_536)
    api_key_ref: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    auth: Literal["auto", "bearer", "x_api_key", "x_goog_api_key", "none"] = "bearer"
    request_dimensions: int | None = Field(default=None, ge=1, le=65_536)
    timeout_seconds: float = Field(default=60.0, ge=0.01, le=600)
    batch_size: int = Field(default=8, ge=1, le=8)
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        try:
            url = urlsplit(value)
            url.port
        except ValueError:
            raise ValueError("Embedding URL must be an HTTP(S) prefix.") from None
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment or "\\" in value
                or any(char.isspace() or ord(char) < 32 for char in value)):
            raise ValueError("Embedding URL must be an HTTP(S) prefix without credentials.")
        return value.rstrip("/")

    @field_validator("model", "label", "model_revision")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or any(ord(char) < 32 for char in value)):
            raise ValueError("Embedding labels and model identifiers require visible text.")
        return value

    @field_validator("extra_body")
    @classmethod
    def valid_extra(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_extra(value)
        try:
            encoded = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Embedding extensions must be finite JSON values.") from None
        if len(encoded) > 32_768:
            raise ValueError("Embedding extensions exceed the size limit.")
        return value

    @model_validator(mode="after")
    def matching_dimensions(self):
        if self.request_dimensions is not None and self.request_dimensions != self.dimension:
            raise ValueError("Requested dimensions must match the validated output dimension.")
        return self


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    schema_version: Literal[1]
    default_profile: str | None = None
    profiles: dict[str, EmbeddingProfile] = Field(max_length=100)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_integer(cls, value):
        if type(value) is not int:
            raise ValueError("Embedding schema version must be an integer.")
        return value


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid or duplicate embedding configuration key.")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class ResolvedEmbeddingProfile:
    profile_id: str
    profile: EmbeddingProfile
    api_key: SecretStr | None
    fingerprint: str


class EmbeddingRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.profiles: dict[str, EmbeddingProfile] = {}
        self.default_profile: str | None = settings.embedding_default_profile
        self.error_code: str | None = None
        try:
            with settings.embedding_config_path.open("rb") as handle:
                raw = handle.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Embedding configuration is too large.")
            document = _Document.model_validate(yaml.load(raw.decode("utf-8-sig"), Loader=_UniqueLoader))
            if any(not _PROFILE_ID.fullmatch(key) for key in document.profiles):
                raise ValueError("Invalid embedding profile identifier.")
            default = settings.embedding_default_profile or document.default_profile
            if default is not None and default not in document.profiles:
                raise ValueError("Default embedding profile must exist.")
            self.default_profile = default
            self.profiles = document.profiles
        except FileNotFoundError:
            self.error_code = "embedding_configuration_missing"
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError, RecursionError):
            self.error_code = "embedding_configuration_invalid"

    def _key(self, profile: EmbeddingProfile) -> SecretStr | None:
        if profile.auth == "none" or profile.api_key_ref is None:
            return None
        value = self.settings.ai_keys.get(profile.api_key_ref.casefold())
        return value if value is not None and value.get_secret_value().strip() else None

    def describe(self) -> dict:
        value = {"enabled": self.settings.rag_enabled, "default_profile": self.default_profile,
                 "items": [{"id": key, "label": profile.label or key, "protocol": profile.protocol,
                            "model": profile.model, "model_revision": profile.model_revision,
                            "dimension": profile.dimension, "enabled": profile.enabled,
                            "configured": profile.auth == "none" or self._key(profile) is not None}
                           for key, profile in self.profiles.items()]}
        if self.error_code:
            value["error_code"] = self.error_code
        return value

    def resolve(self, profile_id: str | None = None) -> ResolvedEmbeddingProfile:
        if not self.settings.rag_enabled:
            raise RagError(503, "rag_disabled")
        if self.error_code:
            raise RagError(503, self.error_code)
        selected = profile_id if profile_id is not None else self.default_profile
        if selected is None:
            raise RagError(503, "embedding_default_profile_missing")
        if selected not in self.profiles:
            raise RagError(422, "embedding_profile_unknown")
        profile = self.profiles[selected]
        if not profile.enabled:
            raise RagError(409, "embedding_profile_disabled")
        key = self._key(profile)
        if profile.auth != "none" and key is None:
            raise RagError(503, "embedding_api_key_missing")
        semantic = profile.model_dump(include={"protocol", "base_url", "model", "model_revision",
                                                "dimension", "request_dimensions", "extra_body"})
        raw = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return ResolvedEmbeddingProfile(selected, profile, key, hashlib.sha256(raw.encode()).hexdigest())
