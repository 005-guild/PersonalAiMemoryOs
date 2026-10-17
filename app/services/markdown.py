"""Versioned Markdown notes with safe YAML and stable content fingerprints."""

import hashlib
import json
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.models.fields import (
    Identifier, Label, Title, MAX_BODY_LENGTH, MAX_CATEGORY_LENGTH,
    MAX_SUMMARY_LENGTH, MAX_TERM_COUNT,
)


class MarkdownError(ValueError):
    """The note does not conform to the supported Markdown format."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that also rejects ambiguous duplicate mapping keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in mapping:
                    raise MarkdownError("Duplicate YAML mapping key.")
                mapping[key] = self.construct_object(value_node, deep=deep)
            except TypeError:
                raise MarkdownError("YAML mapping keys must be scalar values.") from None
        return mapping


def _lf(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


class NoteDocument(BaseModel):
    """The editable, versioned fields of a knowledge note."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    id: Identifier | None = None
    source_id: Identifier | None = None
    title: Title
    summary: str = Field(default="", max_length=MAX_SUMMARY_LENGTH)
    category: str | None = Field(default=None, max_length=MAX_CATEGORY_LENGTH)
    tags: list[Label] = Field(default_factory=list, max_length=MAX_TERM_COUNT)
    concepts: list[Label] = Field(default_factory=list, max_length=MAX_TERM_COUNT)
    body: str = Field(default="", max_length=MAX_BODY_LENGTH)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: Any) -> Any:
        if type(value) is not int or value != 1:
            raise ValueError("Only schema_version 1 is supported.")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The title cannot be empty.")
        return _lf(value)

    @field_validator("summary", "body")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _lf(value)

    @field_validator("tags", "concepts")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_lf(value) for value in values))


def parse_document(text: str) -> NoteDocument:
    """Parse required frontmatter without changing Markdown body whitespace."""
    normalized = _lf(text)
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].removesuffix("\n") != "---":
        raise MarkdownError("The note must start with YAML frontmatter.")
    end = next(
        (index for index in range(1, len(lines)) if lines[index].removesuffix("\n") == "---"),
        None,
    )
    if end is None:
        raise MarkdownError("YAML frontmatter is not closed.")
    try:
        metadata = yaml.load("".join(lines[1:end]), Loader=_UniqueKeyLoader)
    except yaml.YAMLError:
        raise MarkdownError("Invalid or unsafe YAML frontmatter.") from None
    if not isinstance(metadata, dict):
        raise MarkdownError("YAML frontmatter must be a mapping.")
    if "schema_version" not in metadata or "title" not in metadata:
        raise MarkdownError("Frontmatter requires schema_version and title.")
    if "body" in metadata:
        raise MarkdownError("The body must appear below the frontmatter.")
    try:
        return NoteDocument(**metadata, body="".join(lines[end + 1 :]))
    except (ValidationError, TypeError) as exc:
        raise MarkdownError(f"Invalid note metadata: {exc}") from None


def render_document(document: NoteDocument) -> str:
    """Render canonical frontmatter; preserve the body's trailing newlines."""
    metadata = document.model_dump(exclude={"body"})
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    return f"---\n{frontmatter}---\n{_lf(document.body)}"


def document_projection(document: NoteDocument) -> dict:
    """Return editable content, excluding note identity and format metadata."""
    return document.model_dump(exclude={"id", "schema_version"})


def _normalize_projection(value: Any) -> Any:
    if isinstance(value, str):
        return _lf(value)
    if isinstance(value, list):
        return [_normalize_projection(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_projection(item) for key, item in value.items()}
    return value


def content_hash(projection: dict) -> str:
    """Fingerprint semantic content with stable JSON and LF line endings."""
    normalized = _normalize_projection(projection)
    for field in ("tags", "concepts"):
        if isinstance(normalized.get(field), list):
            normalized[field] = list(dict.fromkeys(normalized[field]))
    canonical = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return raw_hash(canonical)


def raw_hash(text: str) -> str:
    """Fingerprint original UTF-8 text, retaining its exact line endings."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
