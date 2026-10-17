"""Safe export parsing preserves text and never reads local files or images."""

import json

import pytest

from app.services.import_types import ImportItemResult, ImportProtocolError, ParsedZhihuItem
from app.services.zhihu_markdown import parse_markdown_document
from app.services.zhihu_parser import normalize_zhihu_url, parse_import_document


def export(*, identity=123, resource="article", body="正文\n", fields="", newline="\n", bom=False):
    url = {"article": f"https://zhuanlan.zhihu.com/p/{identity}",
           "answer": f"https://www.zhihu.com/question/9/answer/{identity}",
           "pin": f"https://www.zhihu.com/pin/{identity}"}[resource]
    header = (f'---\nid: "{identity}"\ntitle: 中文标题\nauthor: 作者\n'
              f'type: zhihu-{resource}\nsource: {url}\n{fields}---\n')
    return ("\ufeff" if bom else "") + header.replace("\n", newline) + body


def raw(files):
    return json.dumps({"files": files}, ensure_ascii=False).encode("utf-8")


def file(content=None, path="export/articles/中文.md"):
    return {"relative_path": path, "content": export() if content is None else content}


@pytest.mark.parametrize("resource", ["article", "answer", "pin"])
@pytest.mark.parametrize("newline,bom", [("\n", False), ("\r\n", True)])
def test_body_preserved_exactly_after_delimiter(resource, newline, bom):
    body = ' \r\n中文、"引号"\r\n```sql\r\nSELECT 1;\r\n```\r\n![图片](images/not-read.jpg)\n\n'
    batch = parse_markdown_document(raw([file(export(resource=resource, newline=newline, bom=bom, body=body))]))
    entry = batch.entries[0]
    assert isinstance(entry, ParsedZhihuItem)
    assert entry.values["content"] == body
    assert entry.values["source_type"] == "zhihu"
    assert entry.resource_type == resource and entry.external_id == "123"
    assert batch.metadata[0]["title"] == "中文标题" and batch.metadata[0]["author"] == "作者"


def test_utf8_bom_outer_json_and_missing_optional_metadata():
    content = "---\ntitle: 无作者\nsource: https://www.zhihu.com/pin/2\n---\n正文"
    batch = parse_markdown_document(b"\xef\xbb\xbf" + raw([file(content)]))
    assert batch.entries[0].values["author"] is None
    assert batch.entries[0].values["content"] == "正文"


def test_export_dates_ignored_without_noise_unknown_fields_warn_without_echo():
    known = "created: 2025-01-01\nupdated: yesterday\ncollected: x\ndownloaded: y\n"
    batch = parse_markdown_document(raw([file(export(fields=known))]))
    assert batch.metadata[0]["warnings"] == []
    batch = parse_markdown_document(raw([file(export(fields="private-body-sentinel: ignored\n"))]))
    assert batch.metadata[0]["warnings"]
    assert "private-body-sentinel" not in json.dumps(batch.metadata)


@pytest.mark.parametrize("content", [
    "no frontmatter private-body-sentinel",
    export().replace("title: 中文标题", "title: [unterminated private-body-sentinel"),
    export(fields="title: duplicate-private-body-sentinel\n"),
    export(fields="extra: !!python/object/apply:os.system [private-body-sentinel]\n"),
    export(fields="extra: &loop [*loop]\n"),
    export(fields="extra: &value x\nother: *value\n"),
    export(fields="extra: " + "[" * 100 + "0" + "]" * 100 + "\n"),
    export(fields="extra: " + "x" * 65536 + "\n"),
], ids=["no-header", "invalid-yaml", "duplicate", "unsafe-tag", "recursive-alias", "alias", "deep", "large-header"])
def test_unsafe_or_invalid_yaml_isolated_and_errors_never_echo_source(content):
    batch = parse_markdown_document(raw([file(content), file(export(identity=2), "other.md")]))
    assert isinstance(batch.entries[0], ImportItemResult) and batch.entries[0].status == "invalid"
    assert isinstance(batch.entries[1], ParsedZhihuItem)
    assert "private-body-sentinel" not in batch.entries[0].model_dump_json()
    assert "private-body-sentinel" not in json.dumps(batch.metadata)


@pytest.mark.parametrize("key,value", [
    ("title", "[]"), ("title", "true"), ("title", "null"), ("title", '""'),
    ("author", "123"), ("author", "{}"), ("source", "[]"), ("source", "false"),
    ("id", "true"), ("id", "123.0"), ("id", "[]"), ("id", "{}"),
    ("id", '"00000000-0000-0000-0000-000000000123"'), ("id", '"124"'),
    ("type", "[]"), ("type", "true"), ("type", "zhihu-answer"),
])
def test_non_scalar_or_mismatched_metadata_invalid(key, value):
    replacements = {"title": "中文标题", "author": "作者", "source": "https://zhuanlan.zhihu.com/p/123",
                    "id": '"123"', "type": "zhihu-article"}
    content = export().replace(f"{key}: {replacements[key]}", f"{key}: {value}")
    assert parse_markdown_document(raw([file(content)])).entries[0].status == "invalid"


def test_numeric_original_id_is_zhihu_identity_not_source_uuid():
    content = export().replace('id: "123"', "id: 123")
    entry = parse_markdown_document(raw([file(content)])).entries[0]
    assert isinstance(entry, ParsedZhihuItem) and entry.external_id == "123"
    assert "id" not in entry.values


@pytest.mark.parametrize("path", ["/absolute.md", "../outside.md", "a/../outside.md", "C:/outside.md",
                                   "a\\outside.md", "a//file.md", "./file.md", "images/test.jpg", "a\x00.md"])
def test_client_paths_are_display_identifiers_never_disk_access(path):
    batch = parse_markdown_document(raw([file(path=path)]))
    assert batch.entries[0].status == "invalid"
    assert batch.metadata[0]["relative_path"] is None


def test_readme_is_ignored_and_duplicate_path_is_reported():
    batch = parse_markdown_document(raw([file("# 目录", "ROOT/README.MD"), file(path="a.md"), file(path="A.MD")]))
    assert batch.entries[0].status == "skipped" and batch.entries[0].reason == "directory_index"
    assert isinstance(batch.entries[1], ParsedZhihuItem)
    assert batch.entries[2].reason == "duplicate_relative_path"


@pytest.mark.parametrize("raw_data,status", [
    (b'\xff', 400), (b'broken', 400), (b'{"files":[],"files":[]}', 400),
    (b'{"files":[NaN]}', 400), (b'[' * 2000 + b'0', 400),
    (b'{"files":[]}', 422), (b'{"files":{}}', 422),
    (b'{"files":[],"schema_version":1}', 422),
    (b' ' * (10 * 1024 * 1024 + 1), 413),
], ids=["encoding", "syntax", "duplicate-key", "nonfinite", "deep", "empty", "wrong-type", "unexpected-schema", "oversize"])
def test_invalid_outer_protocol_rejected_before_rows(raw_data, status):
    with pytest.raises(ImportProtocolError) as error:
        parse_markdown_document(raw_data)
    assert error.value.status_code == status


def test_up_to_1000_files_and_over_500_are_supported():
    files = [file(export(identity=index + 1), f"notes/{index}.md") for index in range(1000)]
    assert len(parse_markdown_document(raw(files)).entries) == 1000
    with pytest.raises(ImportProtocolError) as error:
        parse_markdown_document(raw(files + [file(path="overflow.md")]))
    assert error.value.status_code == 422


def test_invalid_file_reports_safe_filename_and_continues():
    batch = parse_markdown_document(raw([{"relative_path": "bad.md", "content": 123}, file(path="good.md")]))
    assert batch.metadata[0]["relative_path"] == "bad.md"
    assert batch.entries[0].status == "invalid" and isinstance(batch.entries[1], ParsedZhihuItem)


def test_pin_normalization_additive_for_original_json():
    identity = normalize_zhihu_url("HTTP://ZHIHU.COM/pin/123/?tracking=1#fragment")
    assert (identity.resource_type, identity.external_id, identity.canonical_url) == (
        "pin", "123", "https://www.zhihu.com/pin/123")
    entries = parse_import_document(json.dumps({"schema_version": 1, "items": [
        {"url": identity.canonical_url, "title": "想法", "content": "正文"}]}).encode())
    assert entries[0].resource_type == "pin"


@pytest.mark.parametrize("key", ["title", "author", "source", "id", "type"])
def test_yaml_escaped_surrogates_are_invalid_before_metadata_or_database(key):
    replacements = {"title": "中文标题", "author": "作者", "source": "https://zhuanlan.zhihu.com/p/123",
                    "id": '"123"', "type": "zhihu-article"}
    content = export().replace(f"{key}: {replacements[key]}", f'{key}: "\\ud800"')
    batch = parse_markdown_document(raw([file(content), file(export(identity=2), "valid.md")]))
    assert batch.entries[0].status == "invalid" and isinstance(batch.entries[1], ParsedZhihuItem)
    assert batch.metadata[0]["title"] is None and batch.metadata[0]["author"] is None
    assert batch.metadata[0]["url"] is None


def test_original_json_escaped_surrogate_is_also_a_safe_row_error():
    payload = {"schema_version": 1, "items": [{"url": "https://www.zhihu.com/pin/1",
        "title": "\ud800", "content": "do-not-echo-body-sentinel"}]}
    entries = parse_import_document(json.dumps(payload).encode("utf-8"))
    assert entries[0].status == "invalid"
    assert "do-not-echo-body-sentinel" not in entries[0].model_dump_json()
