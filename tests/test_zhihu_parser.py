"""Offline parsing preserves source text and isolates invalid rows."""

import json

import pytest

from app.services.import_types import (
    MAX_IMPORT_BYTES, ImportItemResult, ImportProtocolError, ParsedZhihuItem,
)
from app.services.zhihu_parser import normalize_zhihu_url, parse_import_document


def item(**changes):
    return {"url": "https://www.zhihu.com/question/123/answer/456", "title": "索引学习",
            "author": "示例作者", "content": "第一行\n```sql\nSELECT '中文';\n```\n", **changes}


def encoded(items, **changes):
    return json.dumps({"schema_version": 1, "items": items, **changes}, ensure_ascii=False).encode("utf-8")


def test_utf8_bom_and_markdown_are_preserved():
    value = item(content='  中文\r\n"双引号"与\'单引号\'\n```sql\nSELECT 1;\n```\n')
    parsed = parse_import_document(b"\xef\xbb\xbf" + encoded([value]))[0]
    assert isinstance(parsed, ParsedZhihuItem)
    assert parsed.values["content"] == value["content"]
    assert parsed.values["author"] == value["author"]
    assert parsed.values["source_type"] == "zhihu"


@pytest.mark.parametrize("url,kind,identity,canonical", [
    ("HTTP://WWW.ZHIHU.COM/question/123/answer/456/?utm=abc#section", "answer", "456",
     "https://www.zhihu.com/question/123/answer/456"),
    ("https://zhihu.com/question/123/answer/457", "answer", "457",
     "https://www.zhihu.com/question/123/answer/457"),
    ("http://ZHUANLAN.ZHIHU.COM/p/456/?track=1#part", "article", "456",
     "https://zhuanlan.zhihu.com/p/456"),
])
def test_url_identity_uses_resource_not_question(url, kind, identity, canonical):
    parsed = normalize_zhihu_url(url)
    assert (parsed.resource_type, parsed.external_id, parsed.canonical_url) == (kind, identity, canonical)


@pytest.mark.parametrize("url", [
    "https://evil.example/question/123/answer/456", "https://www.zhihu.com.evil.example/p/123",
    "https://www.zhihu.com/question/123", "https://www.zhihu.com/collection/123",
    "https://www.zhihu.com/video/123", "https://www.zhihu.com/question/1/answer/0",
    "file:///question/123/answer/456", "javascript:alert(1)",
    "https://user:password@www.zhihu.com/question/123/answer/456",
    "https://www.zhihu.com:443/question/123/answer/456",
    "https://www.zhihu.com:invalid/question/123/answer/456",
    "https://www.zhihu.com/question/123/answer/456/extra",
    "https://www.zhihu.com/question/123/answer/456\n?tracking=1",
    "https://www.zhihu.com\\evil/question/123/answer/456",
    "https://www.zhihu.com/question/123/answer/４５６",
])
def test_unsupported_urls_are_not_fetched_or_guessed(url):
    with pytest.raises(ValueError):
        normalize_zhihu_url(url)


@pytest.mark.parametrize("raw", [
    b"not json", b"\xff", b'{"schema_version":1,"items":[NaN]}',
    b'{"schema_version":1,"schema_version":1,"items":[]}',
    b"[" * 2000 + b"0",
], ids=["syntax", "encoding", "nonfinite", "duplicate-key", "deep-incomplete"])
def test_malformed_documents_fail_before_any_row(raw):
    with pytest.raises(ImportProtocolError) as caught:
        parse_import_document(raw)
    assert caught.value.status_code == 400


@pytest.mark.parametrize("document", [
    [], {}, {"schema_version": True, "items": [item()]},
    {"schema_version": "1", "items": [item()]}, {"schema_version": 2, "items": [item()]},
    {"schema_version": 1, "items": []}, {"schema_version": 1, "items": {}},
    {"schema_version": 1, "items": [item()], "unexpected": 1},
    {"schema_version": 1, "items": [item()] * 501},
])
def test_invalid_envelopes_are_rejected(document):
    with pytest.raises(ImportProtocolError) as caught:
        parse_import_document(json.dumps(document).encode())
    assert caught.value.status_code == 422


@pytest.mark.parametrize("invalid", [
    None, "not an item", {}, item(content=" \n\t"), item(content=None),
    item(title=" "), item(title="x" * 501), item(author="x" * 201),
    item(url=None), item(content="x" * 2_000_001), item(extra="private-input-sentinel"),
])
def test_invalid_item_does_not_abort_valid_neighbors(invalid):
    parsed = parse_import_document(encoded([item(), invalid, item(url="https://zhuanlan.zhihu.com/p/789")]))
    assert isinstance(parsed[0], ParsedZhihuItem)
    assert isinstance(parsed[1], ImportItemResult)
    assert parsed[1].index == 1 and parsed[1].status == "invalid"
    assert isinstance(parsed[2], ParsedZhihuItem)
    assert "private-input-sentinel" not in parsed[1].model_dump_json()


def test_body_size_checked_before_decoding():
    with pytest.raises(ImportProtocolError) as caught:
        parse_import_document(b" " * (MAX_IMPORT_BYTES + 1))
    assert caught.value.status_code == 413
