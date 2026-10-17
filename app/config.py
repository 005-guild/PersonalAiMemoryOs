"""Validated configuration and project-relative SQLite paths."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_database_url(database_url: str, *, root: Path | None = None) -> URL:
    """Resolve a plain file-based SQLite URL without opening the database."""
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL must be a valid SQLite URL.") from None

    if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise ValueError("Only file-based SQLite databases are supported.")
    if url.host or url.username or url.password or url.port:
        raise ValueError("SQLite URLs cannot contain a host or credentials.")
    if not url.database or url.database == ":memory:":
        raise ValueError("DATABASE_URL must refer to a persistent SQLite file.")
    if url.database.startswith("file:") or url.query:
        raise ValueError("SQLite URI URLs and query parameters are not supported.")

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = (root if root is not None else PROJECT_ROOT) / database_path
    return url.set(database=str(database_path.resolve()))


class Settings(BaseSettings):
    """Settings from the environment, project .env, and safe defaults."""

    model_config = SettingsConfigDict(
        env_prefix="MEMORY_OS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Desktop explicitly selects a portable root; source/CLI behavior is unchanged.
    runtime_root: Path = Field(default_factory=lambda: PROJECT_ROOT, exclude=True)
    database_url: str = "sqlite:///data/memory.db"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    knowledge_dir: str = "knowledge"
    sync_enabled: bool = True
    sync_interval: float = Field(default=2.0, ge=0.05, le=3600)
    deletion_grace: float = Field(default=10.0, ge=0, le=86400)
    ai_enabled: bool = False
    ai_config_file: str = "config/ai-providers.yml"
    ai_default_profile: str | None = None
    ai_keys: dict[str, SecretStr] = Field(default_factory=dict)
    ai_max_input_chars: int = Field(default=20_000, ge=1, le=2_000_000)
    configuration_read_only: bool = False
    rag_enabled: bool = False
    embedding_config_file: str = "config/embedding-providers.yml"
    embedding_default_profile: str | None = None
    rag_qdrant_url: str = "http://127.0.0.1:6333"
    rag_interval: float = Field(default=5.0, ge=0.05, le=3600)
    rag_chunk_chars: int = Field(default=1200, ge=100, le=8000)
    rag_chunk_overlap: int = Field(default=200, ge=0, le=2000)
    rag_max_note_chars: int = Field(default=100_000, ge=1, le=2_200_000)
    rag_max_chunks: int = Field(default=200, ge=1, le=2000)

    @property
    def embedding_config_path(self) -> Path:
        path = Path(self.embedding_config_file)
        return path if path.is_absolute() else self.runtime_root / path

    @field_validator("embedding_config_file")
    @classmethod
    def validate_embedding_path(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError("EMBEDDING_CONFIG_FILE cannot be empty.")
        path = Path(value)
        root = info.data.get("runtime_root", PROJECT_ROOT)
        path = path if path.is_absolute() else root / path
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("EMBEDDING_CONFIG_FILE must be inside the project.")
        return value

    @field_validator("rag_qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, value: str) -> str:
        from urllib.parse import urlsplit
        try:
            parsed = urlsplit(value)
            parsed.port
        except ValueError:
            raise ValueError("Qdrant URL must be an HTTP(S) prefix.") from None
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or "\\" in value
                or any(character.isspace() or ord(character) < 32 for character in value)):
            raise ValueError("Qdrant URL must be an HTTP(S) prefix without credentials.")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_rag_chunking(self):
        if self.rag_chunk_overlap >= self.rag_chunk_chars:
            raise ValueError("RAG chunk overlap must be smaller than the chunk size.")
        return self

    @property
    def ai_config_path(self) -> Path:
        path = Path(self.ai_config_file)
        return path if path.is_absolute() else self.runtime_root / path

    @field_validator("ai_config_file")
    @classmethod
    def validate_ai_config_file(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError("AI_CONFIG_FILE cannot be empty.")
        path = Path(value)
        root = info.data.get("runtime_root", PROJECT_ROOT)
        path = path if path.is_absolute() else root / path
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("AI_CONFIG_FILE must be inside the project.")
        return value

    @field_validator("ai_keys")
    @classmethod
    def normalize_ai_keys(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        return {key.casefold(): secret for key, secret in value.items()}

    @field_validator("ai_default_profile", "embedding_default_profile", mode="before")
    @classmethod
    def normalize_ai_default_profile(cls, value: str | None) -> str | None:
        return None if value == "" else value

    @property
    def knowledge_path(self) -> Path:
        path = Path(self.knowledge_dir)
        return path if path.is_absolute() else self.runtime_root / path

    @field_validator("knowledge_dir")
    @classmethod
    def validate_knowledge_dir(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError("KNOWLEDGE_DIR cannot be empty.")
        path = Path(value)
        root = info.data.get("runtime_root", PROJECT_ROOT)
        path = path if path.is_absolute() else root / path
        resolved = path.resolve()
        if resolved == root.resolve() or not resolved.is_relative_to(root.resolve()):
            raise ValueError("KNOWLEDGE_DIR must be a subdirectory of the project.")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str, info: ValidationInfo) -> str:
        resolve_database_url(value, root=info.data.get("runtime_root", PROJECT_ROOT))
        return value
