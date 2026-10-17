"""Exercise the public opt-in workflow with isolated, deterministic clients."""

import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import yaml

from app.main import create_app
from app.vector.errors import RagError


class Embeddings:
    def __init__(self):
        self.calls = []

    async def embed(self, resolved, texts):
        self.calls.append(list(texts))
        return SimpleNamespace(vectors=[[1.0, 0.5, 0.25] for _ in texts], usage={"total_tokens": 5})


class Vectors:
    def __init__(self):
        self.collections = {}
        self.metadata = {}

    async def ensure_collection(self, name, dimension, metadata, create=True):
        if name not in self.collections:
            if not create:
                raise RagError(503, "qdrant_collection_missing")
            self.collections[name] = {}
            self.metadata[name] = metadata
        assert self.metadata[name] == metadata and dimension == 3

    async def upsert(self, name, points):
        self.collections[name].update({point["id"]: point for point in points})

    async def query(self, name, vector, limit):
        return [{"id": point["id"], "score": 0.9, "payload": point["payload"]}
                for point in list(self.collections[name].values())[:limit]]

    async def delete_points(self, name, ids):
        for identity in ids:
            self.collections[name].pop(identity, None)

    async def delete_collection(self, name, metadata):
        assert self.metadata[name] == metadata
        self.collections.pop(name, None)


class Answers:
    async def generate(self, resolved, system, user):
        item = json.loads(user)["contexts"][0]
        value = {"insufficient_evidence": False, "paragraphs": [{
            "text": "笔记记录了备份与恢复。", "citations": [{"chunk_id": item["chunk_id"], "quote": "恢复演练"}],
        }]}
        return SimpleNamespace(text=json.dumps(value), usage={"output_tokens": 10})


def wait_for(check):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("Isolated RAG workflow did not converge")


def test_api_index_search_cited_answer_update_delete_and_cached_rebuild(settings, isolated_project):
    directory = isolated_project / "config"
    directory.mkdir()
    for kind in ("embedding", "ai"):
        profile = {"enabled": True, "base_url": "https://example.invalid/v1", "model": "fake", "auth": "none"}
        profile.update({"protocol": "openai_embeddings", "dimension": 3} if kind == "embedding"
                       else {"protocol": "openai_chat", "response_format": "json_object"})
        (directory / f"{kind}-providers.yml").write_text(yaml.safe_dump({
            "schema_version": 1, "default_profile": "fake", "profiles": {"fake": profile}
        }), encoding="utf-8")
    settings = settings.model_copy(update={"rag_enabled": True, "ai_enabled": True, "rag_interval": 3600,
                                           "rag_chunk_chars": 1200, "rag_chunk_overlap": 200})
    vectors, embeddings = Vectors(), Embeddings()
    app = create_app(settings, model_client=Answers(), embedding_client=embeddings, qdrant_client=vectors)

    def trigger(client, endpoint="run"):
        def accepted():
            result = client.post("/api/v1/rag/index/" + endpoint, json={})
            assert result.status_code in (202, 429), result.text
            return result.status_code == 202
        wait_for(accepted)

    with TestClient(app) as client:
        note = client.post("/api/v1/knowledge", json={"title": "备份", "body": "备份应进行恢复演练。"}).json()
        trigger(client)

        def found(marker):
            result = client.post("/api/v1/rag/search", json={"query": "备份"})
            if result.status_code == 503:
                return None
            assert result.status_code in (200, 429), result.text
            if result.status_code != 200:
                return None
            return result.json() if any(marker in item["text"] for item in result.json()["items"]) else None

        result = wait_for(lambda: found("恢复演练"))
        assert result["items"][0]["knowledge_id"] == note["id"]
        answer = client.post("/api/v1/rag/ask", json={"question": "如何核验备份？"})
        assert answer.status_code == 200, answer.text
        assert answer.json()["citations"][0]["quote"] == "恢复演练"
        assert client.get("/api/v1/knowledge").json()["total"] == 1
        assert client.get("/api/v1/processing/runs").json()["total"] == 0
        updated = client.patch("/api/v1/knowledge/" + note["id"], json={
            "expected_version": note["version"], "body": "新版本仍然要求恢复演练。"
        }).json()
        stale = client.post("/api/v1/rag/search", json={"query": "备份"})
        assert stale.status_code == 503 or not stale.json()["items"]
        trigger(client)
        fresh = wait_for(lambda: found("新版本"))
        assert fresh["items"][0]["version"] == updated["version"]
        # The rebuild may re-embed the query, but must reuse note vectors.
        before = sum(any("新版本" in text for text in call) for call in embeddings.calls)
        trigger(client, "rebuild")
        wait_for(lambda: found("新版本"))
        after = sum(any("新版本" in text for text in call) for call in embeddings.calls)
        assert before == after
        deleted = client.delete("/api/v1/knowledge/" + note["id"], params={"expected_version": updated["version"]})
        assert deleted.status_code == 200
        result = client.post("/api/v1/rag/search", json={"query": "备份"})
        assert result.status_code == 200 and result.json()["items"] == []
        answer = client.post("/api/v1/rag/ask", json={"question": "如何核验备份？"})
        assert answer.status_code == 200 and answer.json()["insufficient_evidence"]
