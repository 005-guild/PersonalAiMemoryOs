"""Strict complete-Markdown drafts and exact, selected-source quotations."""

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

from app.agents.errors import AIError
from app.models.fields import Identifier, Label, Title, MAX_BODY_LENGTH, MAX_CATEGORY_LENGTH, MAX_SUMMARY_LENGTH, MAX_TERM_COUNT
from app.services.processing_output import _invalid_number, _unique_keys


class SourceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    source_id: Identifier
    quote: str = Field(min_length=1, max_length=2000)

    @field_validator("quote")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Quote must not be blank.")
        return value


class KnowledgeOutputV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    title: Title
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SUMMARY_LENGTH)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_LENGTH)]
    tags: list[Label] = Field(max_length=MAX_TERM_COUNT)
    concepts: list[Label] = Field(max_length=MAX_TERM_COUNT)
    body: str = Field(min_length=1, max_length=MAX_BODY_LENGTH)
    source_quotes: list[SourceQuote] = Field(min_length=1, max_length=200)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Body must not be blank.")
        return value


def validate_output_v2(text, snapshots):
    try:
        result = KnowledgeOutputV2.model_validate(json.loads(text, object_pairs_hook=_unique_keys,
                                                           parse_constant=_invalid_number)).model_dump()
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, ValidationError, RecursionError, UnicodeError):
        raise AIError(502, "invalid_output") from None
    sources = {source["id"]: source for source in snapshots}
    quoted = set()
    for quote in result["source_quotes"]:
        source = sources.get(quote["source_id"])
        if source is None or quote["quote"] not in source["content"]:
            raise AIError(502, "invalid_evidence")
        quoted.add(source["id"])
    if quoted != set(sources):
        raise AIError(502, "invalid_evidence")
    for key in ("tags", "concepts"):
        result[key] = list(dict.fromkeys(result[key]))
    return result


def render_proposal_v2(result, snapshots):
    # Body is the complete model-authored Markdown, never reconstructed from a short outline.
    return {"source_ids": [source["id"] for source in snapshots], "title": result["title"],
            "summary": result["summary"], "category": result["category"],
            "tags": result["tags"], "concepts": result["concepts"], "body": result["body"]}
