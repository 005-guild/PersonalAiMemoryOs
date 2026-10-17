"""Prompt versions and archived/default behavior without model traffic."""

import hashlib

from app.paths import resource_root
from app.services.prompt_templates import DEEP_ANALYSIS_ID, LEGACY_ID

from processing_v2_helpers import ai_batches

BASE = "/api/v1/prompt-templates"


def test_builtin_original_and_immutable_revision(ai_batches):
    client, app, model = ai_batches
    listing = client.get(BASE).json()
    assert listing["total"] == 2
    builtin = client.get(f"{BASE}/{DEEP_ANALYSIS_ID}").json()
    raw = (resource_root() / "app/prompts/zhihu_deep_analysis_v1.md").read_text(encoding="utf-8")
    assert builtin["content"] == raw
    assert builtin["content_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert builtin["is_default"] and builtin["output_schema_version"] == 2
    original = builtin["content"]
    changed = client.patch(f"{BASE}/{DEEP_ANALYSIS_ID}", json={"expected_version": 1, "content": "新的分析框架"})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    versions = client.get(f"{BASE}/{DEEP_ANALYSIS_ID}/revisions").json()["items"]
    assert [version["version"] for version in versions] == [2, 1]
    assert versions[1]["content"] == original
    assert client.patch(f"{BASE}/{DEEP_ANALYSIS_ID}", json={"expected_version": 1, "name": "过期修改"}).status_code == 409
    app.state.processing.templates.ensure_builtins()
    assert client.get(f"{BASE}/{DEEP_ANALYSIS_ID}").json()["content"] == "新的分析框架"
    assert model.calls == 0


def test_create_copy_default_archive_and_pagination(ai_batches):
    client, _, model = ai_batches
    created = client.post(BASE, json={"name": "我的副本", "content": "独立的框架", "description": "测试用途"})
    assert created.status_code == 201
    template = created.json()
    assert client.get(BASE + "?offset=1&limit=1").json()["total"] == 3
    assert client.post(f"{BASE}/{DEEP_ANALYSIS_ID}/archive", json={"expected_version": 1}).status_code == 409
    default = client.post(f"{BASE}/{template['id']}/default", json={"expected_version": 1})
    assert default.status_code == 200 and default.json()["version"] == 2
    assert client.get(f"{BASE}/{DEEP_ANALYSIS_ID}").json()["is_default"] is False
    archived = client.post(f"{BASE}/{LEGACY_ID}/archive", json={"expected_version": 1})
    assert archived.status_code == 200 and archived.json()["archived_at"]
    assert client.get(BASE).json()["total"] == 2
    assert client.get(BASE + "?include_archived=true").json()["total"] == 3
    assert client.patch(f"{BASE}/{LEGACY_ID}", json={"expected_version": 2, "name": "不能编辑归档"}).status_code == 409
    assert client.post(f"{BASE}/{LEGACY_ID}/default", json={"expected_version": 2}).status_code == 409
    assert model.calls == 0


def test_prompt_validation(ai_batches):
    client, _, model = ai_batches
    for payload in ({"name": " ", "content": "内容"}, {"name": "名称", "content": " "},
                    {"name": "名称", "content": "内容", "unexpected": True},
                    {"name": "名称", "content": "内容", "output_schema_version": 3},
                    {"name": "名称", "content": "x" * 100001}):
        assert client.post(BASE, json=payload).status_code == 422
    assert model.calls == 0
