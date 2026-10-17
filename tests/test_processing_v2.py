"""Exact quotations and complete Markdown output validation."""

import json
from uuid import uuid4

import pytest

from app.agents.errors import AIError
from app.services.processing_v2 import render_proposal_v2, validate_output_v2


def material():
    return [{"id": str(uuid4()), "content": "事实甲。\r\n完整原文乙。"}, {"id": str(uuid4()), "content": "另一篇观点丙。"}]


def output(sources):
    return {"title": "完整分析", "summary": "摘要", "category": "思考", "tags": ["证据", "证据"],
        "concepts": [], "body": "# 第一阶段\n完整正文\n\n```python\nprint('中文')\n```\n",
        "source_quotes": [{"source_id": row["id"], "quote": row["content"]} for row in sources]}


def test_v2_preserves_complete_body_and_all_sources():
    sources = material()
    raw = output(sources)
    result = validate_output_v2(json.dumps(raw), sources)
    assert result["body"] == raw["body"] and result["tags"] == ["证据"]
    proposal = render_proposal_v2(result, sources)
    assert proposal["body"] == raw["body"] and proposal["source_ids"] == [row["id"] for row in sources]


@pytest.mark.parametrize("change", ["unknown_source", "missing_source", "wrong_quote", "empty_quote", "long_quote", "empty_body", "extra", "markdown_fence"])
def test_v2_rejects_untraceable_or_malformed_output(change):
    sources = material()
    raw = output(sources)
    if change == "unknown_source": raw["source_quotes"][0]["source_id"] = str(uuid4())
    if change == "missing_source": raw["source_quotes"].pop()
    if change == "wrong_quote": raw["source_quotes"][0]["quote"] = "原文不存在的句子"
    if change == "empty_quote": raw["source_quotes"][0]["quote"] = " "
    if change == "long_quote": raw["source_quotes"][0]["quote"] = "甲" * 2001
    if change == "empty_body": raw["body"] = " \n"
    if change == "extra": raw["unknown"] = True
    text = json.dumps(raw)
    if change == "markdown_fence": text = "```json\n" + text + "\n```"
    with pytest.raises(AIError) as error:
        validate_output_v2(text, sources)
    assert error.value.code in {"invalid_output", "invalid_evidence"}
