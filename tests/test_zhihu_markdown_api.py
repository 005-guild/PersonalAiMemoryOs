"""HTTP Markdown imports reuse atomic Source-only imports and report metadata."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.models import Knowledge, Source, SourceOrigin, SyncOperation, SyncState, utcnow
from test_zhihu_markdown import export, file

ENDPOINT = "/api/v1/imports/zhihu-markdown"


def test_markdown_preview_import_repeat_difference_and_deleted(client, settings):
    content = export(resource="pin", body="中文\r\n```sql\r\nSELECT 1;\r\n```\r\n")
    payload = {"files": [file(content)]}
    preview = client.post(ENDPOINT + "?dry_run=true", json=payload)
    assert preview.status_code == 200 and preview.json()["would_create"] == 1
    assert client.get("/api/v1/sources").json()["total"] == 0
    first = client.post(ENDPOINT, json=payload).json()
    result = first["items"][0]
    assert first["created"] == 1
    assert result["relative_path"] == payload["files"][0]["relative_path"]
    assert result["title"] == "中文标题" and result["author"] == "作者"
    assert result["url"] == "https://www.zhihu.com/pin/123" and result["warnings"] == []
    assert "content" not in result
    source = client.get("/api/v1/sources/" + result["source_id"]).json()
    assert source["content"] == "中文\r\n```sql\r\nSELECT 1;\r\n```\r\n"
    assert source["id"] != "123"
    again = client.post(ENDPOINT, json=payload).json()
    assert again["created"] == 0 and again["skipped"] == 1
    changed = client.post(ENDPOINT, json={"files": [file(content + "changed")] }).json()
    assert changed["items"][0]["differing_fields"] == ["content"]
    client.delete("/api/v1/sources/" + source["id"], params={"expected_version": source["version"]})
    deleted = client.post(ENDPOINT, json=payload).json()
    assert deleted["items"][0]["reason"] == "deleted_source"
    with client.app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(SourceOrigin)) == 1
        for model in (Knowledge, SyncOperation, SyncState):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert not settings.knowledge_path.exists()


def test_more_than_500_valid_files_dry_run_and_full_1000_envelope(client):
    files = [file(export(identity=index + 1), f"notes/{index}.md") for index in range(501)]
    result = client.post(ENDPOINT + "?dry_run=true", json={"files": files})
    assert result.status_code == 200 and result.json()["would_create"] == 501
    assert client.get("/api/v1/sources").json()["total"] == 0
    files = [file("# index", f"folder{index}/README.md") for index in range(1000)]
    result = client.post(ENDPOINT, json={"files": files})
    assert result.status_code == 200 and result.json()["skipped"] == 1000
    assert client.post(ENDPOINT, json={"files": files + [file(path="1001.md")]}).status_code == 422


@pytest.mark.parametrize("deleted", [False, True])
def test_existing_manual_pin_is_matched_without_takeover(client, deleted):
    database = client.app.state.database
    with database.session() as session:
        source = Source(source_type="manual", title="manual", content="keep",
                        url="http://zhihu.com/pin/123/?legacy=yes#fragment")
        if deleted:
            source.deleted_at = utcnow()
        session.add(source)
        session.commit()
        source_id = source.id
    result = client.post(ENDPOINT, json={"files": [file(export(resource="pin"))]}).json()
    assert result["items"][0]["reason"] == ("legacy_deleted" if deleted else "legacy_match")
    assert result["items"][0]["source_id"] == source_id
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SourceOrigin)) == 0
        assert session.get(Source, source_id).content == "keep"


def test_partial_database_failure_report_retains_metadata_and_committed_sources(client, monkeypatch):
    from app.services.importer import ImportService
    original = ImportService._item

    def failing(self, entry, dry_run, simulated):
        if entry.index == 1:
            raise OperationalError("private-database-sentinel", {}, Exception("secret"))
        return original(self, entry, dry_run, simulated)

    monkeypatch.setattr(ImportService, "_item", failing)
    response = client.post(ENDPOINT, json={"files": [file(path="first.md"),
        file(export(identity=2), "second.md"), file(export(identity=3), "third.md")]})
    assert response.status_code == 503
    report = response.json()["report"]
    assert report["total"] == 3 and report["processed"] == 2 and report["created"] == report["failed"] == 1
    assert report["items"][0]["relative_path"] == "first.md"
    assert report["items"][1]["relative_path"] == "second.md"
    assert "private-database-sentinel" not in response.text and "secret" not in response.text
    assert client.get("/api/v1/sources").json()["total"] == 1


def test_mixed_invalid_files_readme_and_unread_image_links(client):
    body = "![image](../../private-file.png)\n![remote](https://example.invalid/image.png)\n"
    response = client.post(ENDPOINT, json={"files": [file(export(body=body)),
        file("# collection", "README.md"), file("malformed-yaml-private-body-sentinel", "bad.md")]})
    assert response.status_code == 200
    report = response.json()
    assert report["created"] == report["skipped"] == report["invalid"] == 1
    assert "malformed-yaml-private-body-sentinel" not in response.text
    source_id = report["items"][0]["source_id"]
    assert client.get("/api/v1/sources/" + source_id).json()["content"] == body


def test_stream_size_bom_media_and_document_errors(client):
    raw = b"\xef\xbb\xbf" + json.dumps({"files": [file()]}, ensure_ascii=False).encode()
    assert client.post(ENDPOINT, content=raw, headers={"Content-Type": "application/json;charset=utf-8"}).status_code == 200
    assert client.post(ENDPOINT, content=raw).status_code == 415
    assert client.post(ENDPOINT, json={"files": [], "schema_version": 1}).status_code == 422
    assert client.post(ENDPOINT, content=b'{"files":[],"files":[]}',
                       headers={"Content-Type": "application/json"}).status_code == 400
    response = client.post(ENDPOINT, content=(b" " * (1024 * 1024) for _ in range(11)),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_markdown_openapi_is_complete_and_original_report_contract_unchanged(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"][ENDPOINT]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["properties"]["files"]["maxItems"] == 1000
    assert "#/$defs/" not in json.dumps(body)
    response = client.post("/api/v1/imports/zhihu", json={"schema_version": 1, "items": [
        {"url": "https://www.zhihu.com/pin/999", "title": "pin", "content": "text"}]})
    assert response.status_code == 200 and response.json()["created"] == 1
    assert "relative_path" not in response.json()["items"][0]
    assert "warnings" not in response.json()["items"][0]
