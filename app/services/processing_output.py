"""Strict generated knowledge contracts and a reproducible note projection."""

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.agents.errors import AIError
from app.models.fields import (
    Label, Title, MAX_CATEGORY_LENGTH, MAX_SUMMARY_LENGTH, MAX_TERM_COUNT,
)

OUTPUT_SCHEMA_VERSION = 1
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
AnalysisText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class OpinionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    statement: ShortText
    evidence: ShortText
    analysis: AnalysisText


class KnowledgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    title: Title
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SUMMARY_LENGTH)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_LENGTH)]
    tags: list[Label] = Field(max_length=MAX_TERM_COUNT)
    concepts: list[Label] = Field(max_length=MAX_TERM_COUNT)
    key_points: list[ShortText] = Field(max_length=20)
    opinions: list[OpinionOutput] = Field(max_length=20)


def _lf(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys.")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("Non-finite JSON numbers.")


def validate_output(text: str, source_snapshot: dict) -> dict:
    """Accept one complete JSON object; never repair or strip model prose."""
    try:
        payload = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
        result = KnowledgeOutput.model_validate(payload).model_dump()
        # SQLite and Markdown must be able to encode every resulting string.
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, ValidationError, RecursionError, UnicodeError):
        raise AIError(502, "invalid_output") from None
    original = _lf(source_snapshot["content"])
    for opinion in result["opinions"]:
        opinion["evidence"] = _lf(opinion["evidence"])
        if opinion["evidence"] not in original:
            raise AIError(502, "invalid_evidence")
    for field in ("tags", "concepts"):
        result[field] = list(dict.fromkeys(result[field]))
    return result


def render_proposal(result: dict, source_snapshot: dict) -> dict:
    """Freeze the exact ordinary Knowledge fields the user will adopt."""
    sections = ["## 摘要", result["summary"], "## 核心要点"]
    sections.extend(f"- {point}" for point in result["key_points"])
    sections.append("## 原文观点与 AI 分析")
    if not result["opinions"]:
        sections.append("未提取到明确的原文观点。")
    for number, opinion in enumerate(result["opinions"], start=1):
        sections.extend([
            f"### 观点 {number}", opinion["statement"], "原文依据：",
            "\n".join(f"> {line}" for line in opinion["evidence"].split("\n")),
            "AI 分析：", opinion["analysis"],
        ])
    sections.extend(["## 来源", source_snapshot["title"]])
    if source_snapshot.get("author"):
        sections.append(f"作者：{source_snapshot['author']}")
    if source_snapshot.get("url"):
        sections.append(f"原文链接：{source_snapshot['url']}")
    return {
        "source_id": source_snapshot["id"], "title": result["title"],
        "body": _lf("\n\n".join(sections)) + "\n", "summary": _lf(result["summary"]),
        "category": result["category"], "tags": list(result["tags"]),
        "concepts": list(result["concepts"]),
    }
