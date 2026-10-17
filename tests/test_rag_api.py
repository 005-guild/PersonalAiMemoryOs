"""RAG remains opt-in and keeps existing service contracts usable."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_disabled_rag_is_visible_without_breaking_health_or_content(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/api/v1/rag/embedding-profiles").status_code == 200
    status = client.get("/api/v1/rag/index/status")
    assert status.status_code == 200 and status.json()["enabled"] is False
    for path, body in (("search", {"query": "索引"}), ("index/run", {}), ("index/rebuild", {})):
        response = client.post("/api/v1/rag/" + path, json=body)
        assert response.status_code == 503
    note = client.post("/api/v1/knowledge", json={"title": "独立笔记", "body": "正文"})
    assert note.status_code == 201
    assert client.get("/api/v1/knowledge").json()["total"] == 1


@pytest.mark.parametrize("path,body", [
    ("search", {"query": " "}), ("search", {"query": "字" * 2001}),
    ("search", {"query": "索引", "top_k": 11}), ("search", {"query": "索引", "top_k": True}),
    ("ask", {"question": ""}), ("ask", {"question": "索引", "profile_id": "../bad"}),
    ("index/run", {"retry_failed": "false"}),
])
def test_invalid_rag_inputs_are_rejected_before_any_network(client, path, body):
    assert client.post("/api/v1/rag/" + path, json=body).status_code == 422


def test_openapi_exposes_rag_routes_and_typed_search_answer(client, project_version):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["version"] == project_version
    for suffix in ("embedding-profiles", "index/status", "index/run", "index/rebuild", "search", "ask"):
        assert "/api/v1/rag/" + suffix in spec["paths"]
    assert "SearchRead" in spec["components"]["schemas"]
    assert "AnswerRead" in spec["components"]["schemas"]


@pytest.mark.parametrize("values", [
    {"rag_chunk_chars": 100, "rag_chunk_overlap": 100},
    {"rag_qdrant_url": "https://secret:password@example.com"},
    {"rag_qdrant_url": "http://example.com/?key=secret"},
    {"embedding_config_file": "../outside.yml"},
])
def test_rag_settings_reject_invalid_boundaries(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
