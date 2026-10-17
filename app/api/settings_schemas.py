"""Configuration writes never include a path and secrets are write-only."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.agents.configuration import AIProfile


class AIProfileWrite(AIProfile):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")


class AIKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    ref: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    value: SecretStr = Field(max_length=8192)

    @field_validator("ref")
    @classmethod
    def flat_reference(cls, value):
        if "__" in value:
            raise ValueError("Invalid key reference.")
        return value

    @field_validator("value")
    @classmethod
    def safe_secret(cls, value):
        text = value.get_secret_value()
        if text.strip() and (any(ord(char) < 32 or ord(char) == 127 for char in text) or "${" in text):
            raise ValueError("Invalid key value.")
        try:
            text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid key value.") from None
        return value


class AISettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool
    default_profile: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    profiles: list[AIProfileWrite] = Field(max_length=100)
    key_updates: list[AIKeyUpdate] = Field(default_factory=list, max_length=100)
