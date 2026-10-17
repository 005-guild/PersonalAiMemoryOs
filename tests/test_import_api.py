"""HTTP import limits, error contracts and source-only effects."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.models import Knowledge, SyncOperation, SyncState


def document(*items):
    return {"schema_version": 1, "items": list(items) or [{
        "url": "https://www.zhihu.com/question/12/answer/34",
        "title": "测试原文", "content": "中文与换行\n```sql\nSELECT '中文';\n```\n",
    }]}


def test_import_report_and_source_only_side_effects(client, settings):
    report = client.post("/api/v1/imports/zhihu", json=document()).json()
    assert report["total"] == report["processed"] == report["created"] == 1
    source_id = report["items"][0]["source_id"]
    source = client.get(f"/api/v1/sources/{source_id}").json()
    assert source["content"] == document()["items"][0]["content"]
    assert source["source_type"] == "zhihu" and source["version"] == 1
    with client.app.state.database.session() as session:
        for model in (Knowledge, SyncOperation, SyncState):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert not settings.knowledge_path.exists()


def test_preview_and_mixed_validation(client):
    payload = document(document()["items"][0], {"title": "missing URL"})
    preview = client.post("/api/v1/imports/zhihu?dry_run=true", json=payload)
    assert preview.status_code == 200
    assert preview.json()["would_create"] == 1 and preview.json()["invalid"] == 1
    assert client.get("/api/v1/sources").json()["total"] == 0
    response = client.post("/api/v1/imports/zhihu", json=payload)
    assert response.status_code == 200
    assert response.json()["created"] == response.json()["invalid"] == 1


@pytest.mark.parametrize("raw,status", [
    (b"broken", 400), (b"\xff", 400),
    (b'{"schema_version":2,"items":[]}', 422),
    (b'{"schema_version":1,"items":[]}', 422),
])
def test_protocol_errors_never_write_sources(client, raw, status):
    response = client.post("/api/v1/imports/zhihu", content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == status
    assert client.get("/api/v1/sources").json()["total"] == 0


def test_bounded_stream_without_content_length(client):
    def chunks():
        for _ in range(11):
            yield b" " * 1_048_576
    response = client.post("/api/v1/imports/zhihu", content=chunks(),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert client.get("/api/v1/sources").json()["total"] == 0


def test_utf8_bom_and_json_media_type(client):
    raw = b"\xef\xbb\xbf" + json.dumps(document(), ensure_ascii=False).encode("utf-8")
    response = client.post("/api/v1/imports/zhihu", content=raw,
                           headers={"Content-Type": "application/json; charset=utf-8"})
    assert response.status_code == 200 and response.json()["created"] == 1
    assert client.post("/api/v1/imports/zhihu", content=raw).status_code == 415


def test_database_failure_returns_structured_report(client, monkeypatch):
    def unavailable():
        raise OperationalError("private-database-sentinel", None, RuntimeError("secret"))
    monkeypatch.setattr(client.app.state.database, "session", unavailable)
    response = client.post("/api/v1/imports/zhihu", json=document())
    assert response.status_code == 503
    assert response.json()["report"]["created"] == 0
    assert "private-database-sentinel" not in response.text and "secret" not in response.text


def test_openapi_describes_payload_without_broken_local_refs(client, project_version):
    schema = client.get("/openapi.json").json()
    endpoint = schema["paths"]["/api/v1/imports/zhihu"]["post"]
    body = endpoint["requestBody"]["content"]["application/json"]["schema"]
    assert body["properties"]["items"]["maxItems"] == 500
    assert body["properties"]["items"]["items"]["properties"]["url"]
    assert "#/$defs/" not in json.dumps(body)
    assert schema["info"]["version"] == project_version
