"""Persistent call intent, partial failures, explicit retries and multi-source adoption."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import pytest
from sqlalchemy import func, select

from app.api.processing_batches import BatchCreate
from app.models import Knowledge, ProcessingRun, PromptTemplate, Source
from app.services.prompt_templates import DEEP_ANALYSIS_ID, LEGACY_ID

from processing_v2_helpers import ai_batches, batch_payload, source, submit, wait_batch

BASE = "/api/v1/processing/batches"


def test_individual_persists_full_snapshots_defaults_and_zero_knowledge(ai_batches):
    client, _, model = ai_batches
    sources = [source(client, n) for n in range(3)]
    batch = submit(client, sources)
    result = wait_batch(client, batch["id"])
    assert result["counts"]["ready"] == 3 and model.calls == 3
    assert result["generation_settings"] == {"max_output_tokens": 16384, "timeout_seconds": 180.0}
    assert [row["id"] for row in result["source_snapshots"]] == [row["id"] for row in sources]
    assert [item["position"] for item in result["items"]] == [0, 1, 2]
    assert all(item["attempts"] == 1 and len(item["run_ids"]) == 1 for item in result["items"])
    assert client.get("/api/v1/knowledge").json()["total"] == 0
    run = client.get("/api/v1/processing/runs/" + result["items"][0]["run_id"]).json()
    assert run["output_schema_version"] == 2 and run["finish_reason"] == "stop"
    assert run["result"]["body"] == run["proposal"]["body"]
    assert run["result"]["tags"] == ["分析"]
    assert run["usage"] == {"input_tokens": 30, "output_tokens": 60}
    assert client.get(BASE + "?status=completed&limit=1").json()["total"] == 1


def test_merged_adopts_all_sources_atomically_and_repeated_adoption(ai_batches):
    client, _, model = ai_batches
    sources = [source(client, n) for n in range(3)]
    batch = wait_batch(client, submit(client, sources, mode="merged")["id"])
    assert batch["item_count"] == 1 and model.calls == 1
    run_id = batch["items"][0]["run_id"]
    run = client.get("/api/v1/processing/runs/" + run_id).json()
    assert len(run["result"]["source_quotes"]) == 3
    adopted = client.post(f"/api/v1/processing/runs/{run_id}/adopt", json={"expected_version": run["version"]})
    assert adopted.status_code == 201
    assert adopted.json()["knowledge"]["source_ids"] == [row["id"] for row in sources]
    assert client.post(f"/api/v1/processing/runs/{run_id}/adopt", json={"expected_version": 1}).json()["already_adopted"]
    assert client.get("/api/v1/knowledge").json()["total"] == 1


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_secondary_source_changes_forbid_adoption(ai_batches, change):
    client, _, _ = ai_batches
    sources = [source(client, n) for n in range(2)]
    batch = wait_batch(client, submit(client, sources, mode="merged")["id"])
    second = sources[1]
    if change == "edit":
        assert client.patch(f"/api/v1/sources/{second['id']}", json={"expected_version": 1, "content": "修改的来源"}).status_code == 200
    else:
        assert client.delete(f"/api/v1/sources/{second['id']}?expected_version=1").status_code == 200
    run_id = batch["items"][0]["run_id"]
    run = client.get("/api/v1/processing/runs/" + run_id).json()
    assert run["source_stale"]
    assert client.post(f"/api/v1/processing/runs/{run_id}/adopt", json={"expected_version": run["version"]}).status_code == 409
    assert client.get("/api/v1/knowledge").json()["total"] == 0


@pytest.mark.parametrize("behavior,code", [("invalid", "invalid_output"), ("evidence", "invalid_evidence"), ("refusal", "model_refused")])
def test_bad_item_continues_remaining_without_automatic_retry(ai_batches, behavior, code):
    client, _, model = ai_batches
    model.behaviors = [behavior, "valid"]
    batch = wait_batch(client, submit(client, [source(client, 1), source(client, 2)])["id"])
    assert batch["counts"]["failed"] == batch["counts"]["ready"] == 1
    assert batch["items"][0]["error_code"] == code and model.calls == 2
    assert client.post(f"{BASE}/{batch['id']}/continue", json={"expected_version": batch["version"]}).status_code == 409
    assert model.calls == 2
    assert client.post(f"{BASE}/{batch['id']}/retry-failed", json={"expected_version": batch["version"]}).status_code == 200
    retried = wait_batch(client, batch["id"])
    assert retried["counts"]["ready"] == 2 and model.calls == 3
    assert retried["items"][0]["attempts"] == len(retried["items"][0]["run_ids"]) == 2


@pytest.mark.parametrize("behavior", ["truncate", "upstream", "timeout", "system"])
def test_serious_failure_pauses_and_continue_only_pending(ai_batches, behavior):
    client, _, model = ai_batches
    model.behaviors = [behavior]
    batch = wait_batch(client, submit(client, [source(client, 1), source(client, 2)])["id"], "paused")
    assert model.calls == 1 and batch["counts"]["failed"] == batch["counts"]["pending"] == 1
    run = client.get("/api/v1/processing/runs/" + batch["items"][0]["run_id"]).json()
    assert run["failure_stage"]
    if behavior == "truncate":
        assert run["finish_reason"] == "length" and run["usage"] == {"output_tokens": 12}
    assert client.post(f"{BASE}/{batch['id']}/continue", json={"expected_version": 1}).status_code == 409
    assert client.post(f"{BASE}/{batch['id']}/continue", json={"expected_version": batch["version"]}).status_code == 200
    completed = wait_batch(client, batch["id"])
    assert model.calls == 2 and completed["counts"]["failed"] == 1
    assert completed["items"][0]["attempts"] == 1


def test_client_id_idempotency_and_conflicting_request(ai_batches):
    client, _, model = ai_batches
    sources = [source(client)]
    payload = batch_payload(sources)
    first = client.post(BASE, json=payload)
    assert first.status_code == 202
    completed = wait_batch(client, first.json()["id"])
    duplicate = client.post(BASE, json=payload)
    assert duplicate.status_code == 202 and duplicate.json()["id"] == completed["id"]
    assert model.calls == 1
    assert client.post(BASE, json={**payload, "mode": "merged"}).status_code == 409


def test_selection_validation_and_legacy_merged_rejection(ai_batches):
    client, _, model = ai_batches
    selected = source(client)
    payload = batch_payload([selected])
    assert client.post(BASE, json={**payload, "sources": payload["sources"] * 2}).status_code == 422
    assert client.post(BASE, json={**payload, "sources": []}).status_code == 422
    assert client.post(BASE, json={**payload, "sources": payload["sources"] * 21}).status_code == 422
    assert client.post(BASE, json={**payload, "generation_settings": {"max_output_tokens": 131073}}).status_code == 422
    assert client.post(BASE, json={**payload, "generation_settings": {"timeout_seconds": 601}}).status_code == 422
    assert client.post(BASE, json={**payload, "mode": "merged", "prompt_template_id": LEGACY_ID}).status_code == 422
    assert client.patch(f"/api/v1/sources/{selected['id']}", json={"expected_version": 1, "title": "新标题"}).status_code == 200
    assert client.post(BASE, json=payload).status_code == 409
    assert model.calls == 0 and client.get(BASE).json()["total"] == 0


def test_cancel_drains_current_call_and_preserves_ready_draft(ai_batches):
    client, _, model = ai_batches
    model.block = True
    created = submit(client, [source(client, 1), source(client, 2)])
    assert model.started.wait(2)
    current = client.get(f"{BASE}/{created['id']}").json()
    cancelled = client.post(f"{BASE}/{created['id']}/cancel", json={"expected_version": current["version"]})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelling"
    model.release.set()
    result = wait_batch(client, created["id"], "cancelled")
    assert result["counts"]["ready"] == result["counts"]["cancelled"] == 1
    assert model.calls == 1
    assert client.get("/api/v1/processing/runs/" + result["items"][0]["run_id"]).json()["status"] == "ready"


def test_prompt_snapshot_immutable_while_call_and_gate_shared(ai_batches):
    client, app, model = ai_batches
    model.block = True
    selected = source(client)
    batch = submit(client, [selected])
    assert model.started.wait(2)
    assert app.state.generation_gate.acquire(blocking=False) is False
    original = model.captured[0]["system"]
    template = client.get(f"/api/v1/prompt-templates/{DEEP_ANALYSIS_ID}").json()
    assert client.patch(f"/api/v1/prompt-templates/{DEEP_ANALYSIS_ID}", json={"expected_version": template["version"], "content": "修改后的模板"}).status_code == 200
    assert client.patch(f"/api/v1/sources/{selected['id']}", json={"expected_version": 1, "content": "新资料"}).status_code == 200
    assert client.get("/health").status_code == 200
    model.release.set()
    result = wait_batch(client, batch["id"])
    assert result["prompt_snapshot"]["system_prompt"] == original
    assert result["source_snapshots"][0]["content"] == selected["content"]
    assert result["items"][0]["source_stale"]


def test_startup_recovery_pauses_without_repeating_call(ai_batches):
    client, app, model = ai_batches
    selected = source(client)
    payload = BatchCreate.model_validate(batch_payload([selected])).model_dump()
    saved, _ = app.state.processing.batches.store.create(payload)
    resolved = app.state.processing.batches._resolved(saved["id"])
    _, run = app.state.processing.batches.store.begin_item(saved["id"], resolved)
    app.state.processing.recover_interrupted()
    recovered = client.get(f"{BASE}/{saved['id']}").json()
    assert recovered["status"] == "paused" and recovered["counts"]["interrupted"] == 1
    assert client.get("/api/v1/processing/runs/" + run["id"]).json()["status"] == "interrupted"
    assert model.calls == 0
    assert client.post(f"{BASE}/{saved['id']}/continue", json={"expected_version": recovered["version"]}).status_code == 409
    assert client.post(f"{BASE}/{saved['id']}/retry-failed", json={"expected_version": recovered["version"]}).status_code == 200
    assert wait_batch(client, saved["id"])["counts"]["ready"] == 1 and model.calls == 1


def test_request_stop_prevents_next_batch_call(ai_batches):
    client, app, model = ai_batches
    model.block = True
    batch = submit(client, [source(client, 1), source(client, 2)])
    assert model.started.wait(2)
    app.state.processing.request_stop()
    model.release.set()
    paused = wait_batch(client, batch["id"], "paused")
    assert model.calls == 1 and paused["counts"]["ready"] == paused["counts"]["pending"] == 1


@pytest.mark.parametrize("change", ["disabled", "removed", "endpoint", "model", "key_ref", "ai_off"])
def test_resume_requires_same_current_enabled_profile(ai_batches, change):
    client, app, model = ai_batches
    model.behaviors = ["upstream"]
    batch = wait_batch(client, submit(client, [source(client, 1), source(client, 2)])["id"], "paused")
    registry = app.state.ai_registry
    if change == "removed": registry.profiles.clear()
    elif change == "ai_off": registry.settings.ai_enabled = False
    else:
        fields = {"disabled": {"enabled": False}, "endpoint": {"base_url": "https://different.invalid/v1"},
                  "model": {"model": "different-model"}, "key_ref": {"api_key_ref": "different-ref"}}
        registry.profiles["test"] = registry.profiles["test"].model_copy(update=fields[change])
    response = client.post(f"{BASE}/{batch['id']}/continue", json={"expected_version": batch["version"]})
    assert response.status_code in {409, 422, 503}
    assert model.calls == 1
    assert client.get(f"{BASE}/{batch['id']}").json()["status"] == "paused"


def test_same_client_token_concurrent_posts_create_one_call(ai_batches):
    client, _, model = ai_batches
    payload = batch_payload([source(client)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(BASE, json=payload), range(2)))
    assert all(response.status_code == 202 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1
    wait_batch(client, responses[0].json()["id"])
    assert model.calls == 1 and client.get(BASE).json()["total"] == 1


def test_explicit_single_template_and_large_overrides(ai_batches):
    client, _, model = ai_batches
    selected = source(client)
    response = client.post("/api/v1/processing/runs", json={"source_id": selected["id"],
        "expected_source_version": 1, "prompt_template_id": DEEP_ANALYSIS_ID, "prompt_template_version": 1,
        "generation_settings": {"max_output_tokens": 32768, "timeout_seconds": 240}})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["output_schema_version"] == 2 and run["source_count"] == 1
    assert run["generation_settings"] == {"max_output_tokens": 32768, "timeout_seconds": 240.0}
    assert model.captured[0]["profile"]["max_output_tokens"] == 32768
    assert run["prompt_snapshot"]["system_prompt"] == model.captured[0]["system"]


def test_merged_history_filter_includes_secondary_source(ai_batches):
    client, _, _ = ai_batches
    sources = [source(client, 1), source(client, 2)]
    batch = wait_batch(client, submit(client, sources, mode="merged")["id"])
    history = client.get("/api/v1/processing/runs", params={"source_id": sources[1]["id"]}).json()
    assert history["total"] == 1
    assert history["items"][0]["source_count"] == 2
    assert history["items"][0]["source_ids"] == [row["id"] for row in sources]
    assert "source_snapshots" not in history["items"][0]


def test_publication_failure_preserves_uncertain_call_and_does_not_retry(ai_batches, monkeypatch):
    client, app, model = ai_batches
    def unavailable(*args):
        raise RuntimeError("a private database path")
    monkeypatch.setattr(app.state.processing, "_ready", unavailable)
    result = wait_batch(client, submit(client, [source(client, 1), source(client, 2)])["id"], "paused")
    assert result["counts"]["interrupted"] == result["counts"]["pending"] == 1
    run = client.get("/api/v1/processing/runs/" + result["items"][0]["run_id"]).json()
    assert run["status"] == "interrupted" and run["failure_stage"] == "persistence"
    assert model.calls == 1
    assert "private database" not in json.dumps(result)


def test_batch_waiting_for_shared_slot_can_be_cancelled_without_call(ai_batches):
    client, app, model = ai_batches
    assert app.state.generation_gate.acquire(blocking=False)
    try:
        batch = submit(client, [source(client)])
        current = client.get(f"{BASE}/{batch['id']}").json()
        cancelled = client.post(f"{BASE}/{batch['id']}/cancel", json={"expected_version": current["version"]})
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    finally:
        app.state.generation_gate.release()
    assert wait_batch(client, batch["id"], "cancelled")["counts"]["cancelled"] == 1
    assert model.calls == 0


def test_disconnected_submission_still_schedules_saved_intent(ai_batches, monkeypatch):
    client, app, model = ai_batches
    payload = BatchCreate.model_validate(batch_payload([source(client)])).model_dump()
    service = app.state.processing.batches
    original = service.store.create
    committed, release = Event(), Event()
    created_ids = []
    def delayed(value):
        result = original(value)
        created_ids.append(result[0]["id"])
        committed.set()
        assert release.wait(3)
        return result
    monkeypatch.setattr(service.store, "create", delayed)
    async def disconnected():
        caller = asyncio.create_task(service.create(payload))
        assert await asyncio.to_thread(committed.wait, 2)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        release.set()
    try:
        client.portal.call(disconnected)
        result = wait_batch(client, created_ids[0])
        assert result["counts"]["ready"] == 1 and model.calls == 1
    finally:
        release.set()


def test_recovery_reconciles_ready_run_without_repeating_it(ai_batches):
    client, app, model = ai_batches
    sources = [source(client, 1), source(client, 2)]
    service = app.state.processing
    payload = BatchCreate.model_validate(batch_payload(sources)).model_dump()
    saved, _ = service.batches.store.create(payload)
    _, run = service.batches.store.begin_item(saved["id"], service.batches._resolved(saved["id"]))
    proposal = {"source_ids": [sources[0]["id"]], "title": "已成功结果", "body": "完整笔记", "summary": "摘要",
                "category": "分类", "tags": [], "concepts": []}
    result = {key: value for key, value in proposal.items() if key != "source_ids"}
    result["source_quotes"] = [{"source_id": sources[0]["id"], "quote": sources[0]["content"]}]
    service._ready(run["id"], result, proposal, {"output_tokens": 10}, "stop")
    service.recover_interrupted()
    recovered = client.get(f"{BASE}/{saved['id']}").json()
    assert recovered["status"] == "paused" and recovered["counts"]["ready"] == recovered["counts"]["pending"] == 1
    assert model.calls == 0
    assert client.post(f"{BASE}/{saved['id']}/continue", json={"expected_version": recovered["version"]}).status_code == 200
    assert wait_batch(client, saved["id"])["counts"]["ready"] == 2 and model.calls == 1


@pytest.mark.parametrize("mode,change", [("individual", "edit"), ("individual", "delete"), ("merged", "edit"), ("merged", "delete")])
def test_source_changed_while_waiting_never_sends_stale_material(ai_batches, mode, change):
    client, app, model = ai_batches
    sources = [source(client, 1), source(client, 2)]
    assert app.state.generation_gate.acquire(blocking=False)
    try:
        batch = submit(client, sources, mode=mode)
        changed = sources[1]
        if change == "edit":
            assert client.patch(f"/api/v1/sources/{changed['id']}", json={"expected_version": 1, "content": "变更后的资料"}).status_code == 200
        else:
            assert client.delete(f"/api/v1/sources/{changed['id']}?expected_version=1").status_code == 200
    finally:
        app.state.generation_gate.release()
    result = wait_batch(client, batch["id"])
    assert model.calls == (1 if mode == "individual" else 0)
    stale_item = result["items"][-1]
    assert stale_item["error_code"] == "source_stale" and stale_item["status"] == "failed"
    assert stale_item["attempts"] == 0 and stale_item["run_id"] is None


def test_continue_preflights_changed_pending_source_without_call(ai_batches):
    client, _, model = ai_batches
    sources = [source(client, 1), source(client, 2)]
    model.behaviors = ["upstream"]
    batch = wait_batch(client, submit(client, sources)["id"], "paused")
    assert client.patch(f"/api/v1/sources/{sources[1]['id']}", json={"expected_version": 1, "content": "已更改"}).status_code == 200
    assert client.post(f"{BASE}/{batch['id']}/continue", json={"expected_version": batch["version"]}).status_code == 200
    result = wait_batch(client, batch["id"])
    assert model.calls == 1 and result["items"][1]["error_code"] == "source_stale"
