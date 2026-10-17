"""Validated, non-secret provider profiles and environment-backed credentials."""

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
import yaml

from app.agents.errors import AIError
from app.config import Settings

Protocol = Literal[
    "openai_chat", "openai_responses", "anthropic_messages", "gemini_generate_content"
]
AuthMode = Literal["auto", "bearer", "x_api_key", "x_goog_api_key", "none"]
PROFILE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_CONFIG_BYTES = 1024 * 1024

# Check recursively: a nested override is just as consequential as a top-level one.
_RESERVED = {
    "model", "messages", "message", "input", "instructions", "system", "prompt",
    "contents", "systeminstruction", "stream", "streamoptions", "maxtokens",
    "maxcompletiontokens", "maxoutputtokens", "maxinputtokens", "responseformat",
    "format", "tools", "tool", "toolchoice", "functions", "functioncall",
    "apikey", "authorization", "authentication", "auth", "headers", "token",
    "accesstoken", "bearertoken", "credentials", "n", "candidatecount", "store",
    "background", "previousresponseid", "conversation",
    "responsemimetype", "responseschema", "responsejsonschema", "schema", "jsonschema",
}


def _safe_extra(value: Any, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("AI extension parameters are too deeply nested.")
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("AI extension parameter names must be strings.")
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in _RESERVED:
                raise ValueError("AI extension parameters cannot override protected fields.")
            if normalized == "generationconfig" and (key != "generationConfig" or not isinstance(nested, dict)):
                raise ValueError("Gemini generationConfig extensions must be an object using the canonical name.")
            _safe_extra(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _safe_extra(nested, depth + 1)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("AI extension parameters must be JSON values.")


class AIProfile(BaseModel):
    """A single text-generation endpoint; secrets belong in Settings only."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    label: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool = True
    protocol: Protocol
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    api_key_ref: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    auth: AuthMode = "auto"
    response_format: Literal["prompt", "json_object"] = "prompt"
    max_output_tokens: int = Field(default=4096, ge=1, le=131072)
    timeout_seconds: float = Field(default=90.0, ge=0.01, le=600)
    token_limit_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    anthropic_version: str = Field(default="2023-06-01", pattern=r"^\d{4}-\d{2}-\d{2}$")
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
            raise ValueError("AI_BASE_URL must be an HTTP(S) API prefix.")
        try:
            url = urlsplit(value)
            url.port
        except ValueError:
            raise ValueError("AI_BASE_URL must be an HTTP(S) API prefix.") from None
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise ValueError("AI_BASE_URL must be an HTTP(S) API prefix without credentials or query.")
        return value.rstrip("/")

    @field_validator("model", "label")
    @classmethod
    def validate_nonblank(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or any(ord(char) < 32 for char in value)):
            raise ValueError("AI model and label must contain visible text.")
        return value

    @field_validator("extra_body")
    @classmethod
    def validate_extra(cls, value: dict[str, Any]) -> dict[str, Any]:
        _safe_extra(value)
        try:
            encoded = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("AI extension parameters must be finite JSON values.") from None
        if len(encoded) > 32_768:
            raise ValueError("AI extension parameters exceed the size limit.")
        return value


class _ProfileDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    schema_version: Literal[1]
    default_profile: str | None = None
    profiles: dict[str, AIProfile] = Field(max_length=100)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_schema_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("AI schema version must be an integer.")
        return value


@dataclass(frozen=True)
class ResolvedProfile:
    profile_id: str
    profile: AIProfile
    api_key: SecretStr | None
    fingerprint: str


class _UniqueKeysLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError("Duplicate or invalid AI configuration key.")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_UniqueKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


class AIRegistry:
    """Read configuration once; invalid/missing AI config leaves the base service usable."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.profiles: dict[str, AIProfile] = {}
        self.default_profile: str | None = settings.ai_default_profile
        self.error_code: str | None = None
        try:
            with settings.ai_config_path.open("rb") as handle:
                raw = handle.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ValueError("AI configuration exceeds the size limit.")
            value = yaml.load(raw.decode("utf-8-sig"), Loader=_UniqueKeysLoader)
            document = _ProfileDocument.model_validate(value)
            if any(not PROFILE_ID.fullmatch(key) for key in document.profiles):
                raise ValueError("Invalid AI profile identifier.")
            for profile in document.profiles.values():
                if profile.response_format != "prompt" and profile.protocol != "openai_chat":
                    raise ValueError("JSON object mode is supported only by Chat profiles.")
                if profile.protocol != "openai_chat" and profile.token_limit_field != "max_tokens":
                    raise ValueError("Chat token field does not apply to this protocol.")
            default = settings.ai_default_profile or document.default_profile
            if default is not None and default not in document.profiles:
                raise ValueError("Default AI profile must name a configured profile.")
            self.profiles = document.profiles
            self.default_profile = default
        except FileNotFoundError:
            self.error_code = "ai_configuration_missing"
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError, RecursionError):
            self.error_code = "ai_configuration_invalid"

    def _key(self, profile: AIProfile) -> SecretStr | None:
        if profile.auth == "none" or profile.api_key_ref is None:
            return None
        value = self.settings.ai_keys.get(profile.api_key_ref.casefold())
        return value if value is not None and value.get_secret_value().strip() else None

    def _configured(self, profile: AIProfile) -> bool:
        return profile.auth == "none" or self._key(profile) is not None

    def describe(self) -> dict:
        result = {
            "enabled": self.settings.ai_enabled,
            "max_input_chars": self.settings.ai_max_input_chars,
            "default_profile": self.default_profile,
            "items": [
                {"id": key, "label": profile.label or key, "protocol": profile.protocol,
                 "model": profile.model, "enabled": profile.enabled,
                 "configured": self._configured(profile)}
                for key, profile in self.profiles.items()
            ],
        }
        if self.error_code:
            result["error_code"] = self.error_code
        return result

    def resolve(self, profile_id: str | None = None) -> ResolvedProfile:
        if not self.settings.ai_enabled:
            raise AIError(503, "ai_disabled")
        if self.error_code:
            raise AIError(503, self.error_code)
        selected = profile_id if profile_id is not None else self.default_profile
        if selected is None:
            raise AIError(503, "ai_default_profile_missing")
        if selected not in self.profiles:
            raise AIError(422, "ai_profile_unknown")
        profile = self.profiles[selected]
        if not profile.enabled:
            raise AIError(409, "ai_profile_disabled")
        if not self._configured(profile):
            raise AIError(503, "ai_api_key_missing")
        serialized = json.dumps(profile.model_dump(), ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False)
        return ResolvedProfile(selected, profile, self._key(profile),
                               hashlib.sha256(serialized.encode("utf-8")).hexdigest())
