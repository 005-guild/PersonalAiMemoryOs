"""Markdown round trips, safe YAML, and semantic versus raw fingerprints."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import KnowledgeCreate
from app.models.fields import (
    MAX_BODY_LENGTH, MAX_CATEGORY_LENGTH, MAX_SUMMARY_LENGTH, MAX_TERM_COUNT,
    MAX_TERM_LENGTH, MAX_TITLE_LENGTH,
)

from app.services.markdown import (
    MarkdownError,
    NoteDocument,
    content_hash,
    document_projection,
    parse_document,
    raw_hash,
    render_document,
)


@pytest.mark.parametrize("body", ["", "正文", "# 标题\n\n内容\n", "abc\n\n", "\nabc"])
def test_round_trip_preserves_body_and_unicode_metadata(body: str) -> None:
    document = NoteDocument(
        id=str(uuid4()),
        source_id=str(uuid4()),
        title="笔记: 学习与决策",
        summary="第一行\n第二行",
        category="个人知识",
        tags=["学习", "yes", "#tag"],
        concepts=["认知模型"],
        body=body,
    )

    rendered = render_document(document)

    assert rendered.startswith("---\nschema_version: 1\n")
    assert parse_document(rendered) == document
    assert parse_document(rendered).body == body


def test_minimal_frontmatter_accepts_missing_identity_and_nullable_source() -> None:
    document = parse_document("---\nschema_version: 1\ntitle: Minimal\nsource_id: null\n---\nabc")

    assert document.id is None
    assert document.source_id is None
    assert document.summary == ""
    assert document.tags == []
    assert document.concepts == []
    assert document.body == "abc"


def test_crlf_is_normalized_without_adding_a_body_newline() -> None:
    document = parse_document("---\r\nschema_version: 1\r\ntitle: Test\r\n---\r\nabc\r\ndef")

    assert document.body == "abc\ndef"
    assert render_document(document).endswith("---\nabc\ndef")


def test_utf8_bom_from_an_editor_is_accepted() -> None:
    assert parse_document("\ufeff---\nschema_version: 1\ntitle: BOM\n---\n").title == "BOM"


@pytest.mark.parametrize(
    "text",
    [
        "# A note without frontmatter",
        "---\nschema_version: 1\ntitle: Never closed",
        "---\n- schema_version\n- title\n---\n",
        "---\nnull\n---\n",
        "---\ntitle: Missing version\n---\n",
        "---\nschema_version: 1\n---\n",
        "---\nschema_version: 2\ntitle: Unsupported\n---\n",
        "---\nschema_version: true\ntitle: Unsupported\n---\n",
        "---\nschema_version: 1.0\ntitle: Unsupported\n---\n",
        "---\nschema_version: 1\ntitle: ''\n---\n",
        "---\nschema_version: 1\ntitle: '   '\n---\n",
        "---\nschema_version: 1\ntitle: 123\n---\n",
        "---\nschema_version: 1\ntitle: Test\ntags: scalar\n---\n",
        "---\nschema_version: 1\ntitle: Test\nconcepts: [true]\n---\n",
        "---\nschema_version: 1\ntitle: Test\nid: invalid-id\n---\n",
        "---\nschema_version: 1\ntitle: Test\nsource_id: invalid-id\n---\n",
        "---\nschema_version: 1\ntitle: Test\nunknown_field: ignored?\n---\n",
        "---\nschema_version: 1\ntitle: Test\nbody: ambiguous\n---\nactual",
        "---\nschema_version: 1\ntitle: First\ntitle: Second\n---\n",
        "---\nschema_version: 1\ntitle: Test\nsummary: !!python/object:builtins.object {}\n---\n",
        "---\nschema_version: 1\ntitle: [unclosed\n---\n",
    ],
)
def test_invalid_or_unsafe_frontmatter_is_rejected(text: str) -> None:
    with pytest.raises(MarkdownError):
        parse_document(text)


def test_duplicate_nested_mapping_keys_are_rejected() -> None:
    with pytest.raises(MarkdownError):
        parse_document(
            "---\nschema_version: 1\ntitle: Test\ncategory: {name: first, name: second}\n---\n"
        )


def test_projection_excludes_identity_but_tracks_source_relation() -> None:
    source_id = str(uuid4())
    document = NoteDocument(id=str(uuid4()), source_id=source_id, title="Test", body="abc")

    projection = document_projection(document)

    assert set(projection) == {"source_id", "title", "summary", "category", "tags", "concepts", "body"}
    assert projection["source_id"] == source_id
    assert projection["body"] == "abc"
    assert content_hash(projection) == content_hash(
        document_projection(document.model_copy(update={"id": str(uuid4())}))
    )
    assert content_hash(projection) != content_hash(
        document_projection(document.model_copy(update={"source_id": None}))
    )


def test_semantic_hash_uses_stable_json_lf_and_ordered_term_deduplication() -> None:
    first = {"body": "第一行\r\n第二行", "tags": ["a", "b", "a"], "concepts": ["x", "x"]}
    second = {"concepts": ["x"], "tags": ["a", "b"], "body": "第一行\n第二行"}

    assert content_hash(first) == content_hash(second)
    assert first["tags"] == ["a", "b", "a"]
    assert content_hash(first) != content_hash({**second, "tags": ["b", "a"]})
    assert content_hash(first) != content_hash({**second, "body": "第一行\n第二行\n"})


def test_frontmatter_formatting_changes_raw_but_not_semantic_hash() -> None:
    original = "---\nschema_version: 1\ntitle: Test\n---\nabc"
    reformatted = "---\ntitle: 'Test'\nschema_version: 1\n---\nabc"

    assert raw_hash(original) != raw_hash(reformatted)
    assert content_hash(document_projection(parse_document(original))) == content_hash(
        document_projection(parse_document(reformatted))
    )
    assert raw_hash("abc\r\n") != raw_hash("abc\n")


def test_uuid_strings_are_canonicalized() -> None:
    identifier = uuid4()
    document = NoteDocument(id=identifier.hex.upper(), title="UUID")

    assert document.id == str(identifier)


def test_http_and_markdown_share_title_term_and_identifier_normalization() -> None:
    source_id = uuid4()
    values = {"title": "  统一标题  ", "tags": [" SQL "], "source_id": source_id.hex.upper()}
    api = KnowledgeCreate(**values)
    note = NoteDocument(**values)
    assert api.title == note.title == "统一标题"
    assert api.tags == note.tags == ["SQL"]
    assert api.source_id == note.source_id == str(source_id)


@pytest.mark.parametrize("values", [
    pytest.param({"title": "x" * (MAX_TITLE_LENGTH + 1)}, id="title-too-long"),
    pytest.param({"body": "x" * (MAX_BODY_LENGTH + 1)}, id="body-too-long"),
    pytest.param({"summary": "x" * (MAX_SUMMARY_LENGTH + 1)}, id="summary-too-long"),
    pytest.param({"category": "x" * (MAX_CATEGORY_LENGTH + 1)}, id="category-too-long"),
    pytest.param({"tags": ["x" * (MAX_TERM_LENGTH + 1)]}, id="tag-too-long"),
    pytest.param({"concepts": ["x"] * (MAX_TERM_COUNT + 1)}, id="too-many-concepts"),
    pytest.param({"tags": ["   "]}, id="empty-tag"),
])
def test_http_and_markdown_reject_the_same_content_bounds(values: dict) -> None:
    for model in (KnowledgeCreate, NoteDocument):
        with pytest.raises(ValidationError):
            model(**{"title": "Valid", **values})


def test_shared_limits_accept_the_boundary_without_changing_body_newlines() -> None:
    values = {
        "title": "x" * MAX_TITLE_LENGTH,
        "body": "x" * (MAX_BODY_LENGTH - 2) + "\n\n",
        "summary": "x" * MAX_SUMMARY_LENGTH,
        "category": "x" * MAX_CATEGORY_LENGTH,
        "tags": [str(index) for index in range(MAX_TERM_COUNT)],
    }
    api, note = KnowledgeCreate(**values), NoteDocument(**values)
    assert note.body == api.body
    assert parse_document(render_document(note)).body == values["body"]
