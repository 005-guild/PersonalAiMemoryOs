"""Synthetic batch inputs and deterministic model replies, never real network I/O."""

import asyncio
import json
from threading import Event
from types import SimpleNamespace
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.agents.errors import AIError
from app.main import create_app


class BatchModel:
    def __init__(self):
        self.calls, self.behaviors, self.captured = 0, [], []
        self.started, self.release = Event(), Event()
        self.block = False

    async def generate(self, resolved, system, user):
        self.calls += 1
        self.captured.append({"profile": resolved.profile.model_dump(), "system": system, "user": json.loads(user)})
        self.started.set()
        if self.block:
            assert await asyncio.to_thread(self.release.wait, 5)
        behavior = self.behaviors.pop(0) if self.behaviors else "valid"
        if behavior in {"refusal", "truncate", "upstream", "timeout"}:
            code = {"refusal": "model_refused", "truncate": "model_output_truncated", "upstream": "ai_upstream_error", "timeout": "ai_timeout"}[behavior]
            error = AIError(504 if behavior == "timeout" else 502, code)
            error.usage, error.finish_reason = {"output_tokens": 12}, "length" if behavior == "truncate" else None
            raise error
        if behavior == "system":
            raise RuntimeError("untrusted model detail must not escape")
        sources = json.loads(user)["sources"]
        result = {"title": "八阶段分析", "summary": "明确区分事实与判断。", "category": "独立思考",
            "tags": ["分析", "分析"], "concepts": ["证据"], "body": "# 完整深度分析\n\n## 理解\n保留完整正文。\n",
            "source_quotes": [{"source_id": source["id"], "quote": source["content"][:30]} for source in sources]}
        if behavior == "invalid":
            result = {}
        elif behavior == "evidence":
            result["source_quotes"][0]["quote"] = "未出现在原文里的引文"
        return SimpleNamespace(text=json.dumps(result, ensure_ascii=False), usage={"input_tokens": 30, "output_tokens": 60}, finish_reason="stop")


@pytest.fixture
def ai_batches(settings, isolated_project):
    profile = isolated_project / "batch-providers.yml"
    profile.write_text("schema_version: 1\ndefault_profile: test\nprofiles:\n  test:\n"
        "    protocol: openai_chat\n    base_url: https://never-called.invalid/v1\n"
        "    model: fixture-model\n    auth: none\n", encoding="utf-8")
    model = BatchModel()
    application = create_app(settings.model_copy(update={"ai_enabled": True, "ai_config_file": str(profile)}), model_client=model)
    with TestClient(application) as client:
        try:
            yield client, application, model
        finally:
            model.release.set()


def source(client, number=1):
    response = client.post("/api/v1/sources", json={"title": f"来源{number}", "author": f"作者{number}",
        "content": f"作者{number}认为必须保留原文证据，同时审视推论的适用边界。\n这是独立资料。"})
    assert response.status_code == 201
    return response.json()


def batch_payload(sources, **changes):
    return {"client_request_id": str(uuid4()), "mode": "individual",
            "sources": [{"source_id": row["id"], "expected_version": row["version"]} for row in sources], **changes}


def submit(client, sources, **changes):
    response = client.post("/api/v1/processing/batches", json=batch_payload(sources, **changes))
    assert response.status_code == 202, response.text
    return response.json()


def wait_batch(client, identifier, status="completed"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get("/api/v1/processing/batches/" + identifier)
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] == status:
            return result
        time.sleep(.01)
    raise AssertionError(f"Batch did not reach {status}: {result}")
