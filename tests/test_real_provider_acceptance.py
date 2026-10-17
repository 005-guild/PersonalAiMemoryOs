"""Live-acceptance preparation is bounded and never needs a real API key."""

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

from pydantic import SecretStr
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from real_provider_report import Evidence, LiveBudgetGuard, MAX_CALLS
from real_provider_workflow import AcceptanceAPI, AcceptanceFailure
import verify_real_provider as runner

SECRET = "offline-test-only-private-credential"


@pytest.fixture
def prepared(settings, isolated_project):
    target = isolated_project / "examples"
    target.mkdir()
    shutil.copyfile(ROOT / "examples/real-provider-acceptance.json", target / "real-provider-acceptance.json")
    profile = isolated_project / "providers.yml"
    profile.write_text(yaml.safe_dump({
        "schema_version": 1, "default_profile": "deepseek", "profiles": {"deepseek": {
            "protocol": "openai_chat", "base_url": "https://example.invalid/v1", "model": "test-model",
            "api_key_ref": "deepseek", "response_format": "json_object",
        }},
    }), encoding="utf-8")
    return settings.model_copy(update={"ai_enabled": False, "ai_config_file": str(profile)}), isolated_project


def test_missing_key_run_sends_nothing_and_never_starts_a_runtime(prepared):
    settings, root = prepared

    class ForbiddenRuntime:
        def __init__(self, *args):
            pytest.fail("Missing credentials must not start subprocesses or containers")

    status, workspace = runner.execute("run", project_root=root, settings=settings,
                                       runtime_types=(ForbiddenRuntime, ForbiddenRuntime))
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    assert status == 2 and report["status"] == "waiting_for_credentials"
    assert report["actual_model_calls"] == 0 and report["attempts"] == []
    assert report["formal_ai_changed"] is False and not settings.ai_enabled


def test_ready_check_is_still_zero_calls_and_creates_unapproved_review(prepared):
    settings, root = prepared
    settings = settings.model_copy(update={"ai_keys": {"deepseek": SecretStr(SECRET)}})
    status, workspace = runner.execute("check", project_root=root, settings=settings)
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    review = json.loads((workspace / "quality-review.json").read_text(encoding="utf-8"))
    assert status == 0 and report["status"] == "ready_for_live_acceptance"
    assert report["actual_model_calls"] == 0 and report["attempts"] == []
    assert report["quality_accepted"] is False and review["all_passed"] is False
    assert all(case["passed"] is None for case in review["cases"])
    assert SECRET not in "".join(path.read_text(encoding="utf-8") for path in workspace.rglob("*") if path.is_file())


def test_formal_ai_must_stay_disabled_during_acceptance(prepared):
    settings, _ = prepared
    report, resolved = runner.preflight(settings.model_copy(update={"ai_enabled": True}))
    assert resolved is None and report["error_code"] == "formal_ai_must_remain_disabled"


def test_profile_copy_contains_no_secret_and_fixes_approved_limits(prepared):
    settings, root = prepared
    settings = settings.model_copy(update={"ai_keys": {"deepseek": SecretStr(SECRET)}})
    _, resolved = runner.preflight(settings)
    workspace = root / "stage"
    workspace.mkdir()
    path, environment = runner.prepare_profile(workspace, resolved)
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))["profiles"]["deepseek"]
    assert profile["max_output_tokens"] == 2048 and profile["timeout_seconds"] == 90
    assert profile["extra_body"]["thinking"] == {"type": "disabled"}
    assert profile["response_format"] == "json_object"
    assert environment["MEMORY_OS_AI_KEYS__DEEPSEEK"] == SECRET
    assert SECRET not in path.read_text(encoding="utf-8")
    assert resolved.profile.max_output_tokens == 4096


def test_call_reservation_is_persisted_and_cannot_exceed_three(isolated_project):
    evidence = Evidence(isolated_project, {"id": "deepseek"}, {})
    for number in range(MAX_CALLS):
        evidence.reserve(str(number), "local" if number == 0 else "docker", "source-id")
        saved = json.loads(evidence.path.read_text(encoding="utf-8"))
        assert saved["attempts"][-1]["status"] == "outcome_unknown"
        assert len(saved["attempts"]) == number + 1
    with pytest.raises(RuntimeError, match="budget"):
        evidence.reserve("fourth", "docker", "source-id")


@pytest.mark.parametrize("path", ["/api/v1/processing/runs", "/api/v1/processing/runs/", "/api/v1/processing/runs?x=1"])
def test_unguarded_generation_is_rejected(isolated_project, path):
    evidence = Evidence(isolated_project, {}, {})
    api = AcceptanceAPI("http://127.0.0.1:1", isolated_project, evidence)
    with pytest.raises(AcceptanceFailure, match="unguarded"):
        api.request("post", path, {})


def test_timeout_consumes_one_reservation_and_is_not_retried(isolated_project, monkeypatch):
    evidence = Evidence(isolated_project, {}, {})
    api = AcceptanceAPI("http://127.0.0.1:1", isolated_project, evidence)
    calls = []

    def fail(*args):
        calls.append(args)
        raise AcceptanceFailure("acceptance_http_failure")

    monkeypatch.setattr(api, "_request", fail)
    with pytest.raises(AcceptanceFailure):
        api.generate_once({"id": "case", "environment": "local"}, {"id": "source", "version": 1})
    assert len(calls) == len(evidence.data["attempts"]) == 1
    assert evidence.data["attempts"][0]["status"] == "outcome_unknown"


def test_evidence_redacts_secret_including_nested_keys(isolated_project):
    evidence = Evidence(isolated_project, {}, {}, (SECRET,))
    evidence.artifact("draft.json", {SECRET: [{"text": "unexpected echo " + SECRET}]})
    assert SECRET not in (isolated_project / "draft.json").read_text(encoding="utf-8")
    assert "[REDACTED]" in (isolated_project / "draft.json").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        evidence.artifact("../outside.json", {})


def test_runner_alternates_same_storage_and_never_accepts_quality_automatically(prepared, monkeypatch):
    settings, root = prepared
    settings = settings.model_copy(update={"ai_keys": {"deepseek": SecretStr(SECRET)}})
    events = []

    class Runtime:
        def __init__(self, workspace, profile, environment):
            self.workspace = workspace
            self.vault = workspace / "knowledge"
            self.base_url = "http://127.0.0.1:1"
            self.active = False

        def migrate(self):
            events.append("migrate")

        def start(self):
            assert not self.active
            self.active = True
            events.append(("start", str(self.workspace)))

        def stop(self):
            if self.active:
                events.append("stop")
                self.active = False

    monkeypatch.setattr(runner, "check_runtime", lambda runtime, evidence: SimpleNamespace(evidence=evidence))

    def check_case(api, case):
        api.evidence.reserve(case["id"], case["environment"], "source")
        api.evidence.generation_result(201, {"id": case["id"], "usage": {"output_tokens": 100}})
        api.evidence.data["cases"].append({"id": case["id"], "workflow_passed": True})
        api.evidence.save()

    monkeypatch.setattr(runner, "check_case", check_case)
    monkeypatch.setattr(runner, "check_persistence", lambda api: events.append("persistence"))
    status, workspace = runner.execute("run", project_root=root, settings=settings, runtime_types=(Runtime, Runtime))
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    assert status == 0 and report["status"] == "awaiting_quality_review"
    assert len(report["attempts"]) == 3 and report["reserved_model_calls"] == 3
    assert report["quality_accepted"] is False and report["formal_storage_unchanged"] is True
    assert events.count("migrate") == 1 and events.count("stop") == 3
    assert len({event[1] for event in events if isinstance(event, tuple)}) == 1


def test_unrecognized_mode_cannot_start_live_calls(prepared):
    settings, root = prepared
    with pytest.raises(ValueError):
        runner.execute("typo", project_root=root, settings=settings)


def test_another_process_cannot_claim_live_budget(isolated_project):
    one, two = isolated_project / "one", isolated_project / "two"
    one.mkdir()
    two.mkdir()
    guard = LiveBudgetGuard(one)
    guard.acquire()
    try:
        with pytest.raises(RuntimeError):
            LiveBudgetGuard(two).acquire()
    finally:
        guard.release()
    assert not (isolated_project / ".live.lock").exists()


def test_a_previous_unknown_outcome_blocks_a_new_live_execution(isolated_project):
    one, two = isolated_project / "one", isolated_project / "two"
    one.mkdir()
    two.mkdir()
    Evidence(one, {}, {}).reserve("first", "local", "source")
    with pytest.raises(RuntimeError, match="review"):
        LiveBudgetGuard(two).acquire()
    assert not (isolated_project / ".live.lock").exists()
