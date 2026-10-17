"""Preflight or run three isolated DeepSeek calls; never enable formal AI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from app.agents.configuration import AIRegistry
from app.agents.errors import AIError
from app.config import Settings
from real_provider_report import Evidence, LiveBudgetGuard, new_workspace, storage_fingerprint, timestamp
from real_provider_workflow import AcceptanceAPI, AcceptanceFailure, check_case, check_persistence


def preflight(settings: Settings) -> tuple[dict, object | None]:
    # Resolve a test-only Settings copy. The actual service stays disabled.
    registry = AIRegistry(settings.model_copy(update={"ai_enabled": True}))
    profile = registry.profiles.get("deepseek")
    result = {"id": "deepseek", "formal_ai_enabled": settings.ai_enabled,
              "configured": False, "error_code": None}
    if settings.ai_enabled:
        result["error_code"] = "formal_ai_must_remain_disabled"
        return result, None
    if profile is not None:
        result.update(protocol=profile.protocol, model=profile.model, base_url=profile.base_url,
                      response_format=profile.response_format,
                      max_output_tokens=2048, timeout_seconds=90)
    try:
        resolved = registry.resolve("deepseek")
        if resolved.profile.protocol != "openai_chat" or resolved.api_key is None:
            raise AIError(503, "deepseek_configuration_required")
    except AIError as error:
        result["error_code"] = error.code
        return result, None
    result["configured"] = True
    return result, resolved


def load_cases(project_root: Path) -> list[dict]:
    document = json.loads((project_root / "examples/real-provider-acceptance.json").read_text(encoding="utf-8"))
    cases = document["cases"]
    if (document["schema_version"] != 1 or len(cases) != 3
            or [case["environment"] for case in cases] != ["local", "docker", "docker"]
            or len({case["id"] for case in cases}) != 3):
        raise ValueError("Use the three reviewed acceptance cases in local/docker order.")
    return cases


def prepare_profile(workspace: Path, resolved) -> tuple[Path, dict[str, str]]:
    profile = resolved.profile.model_dump()
    profile.update(enabled=True, max_output_tokens=2048, timeout_seconds=90.0,
                   response_format="json_object")
    # The approved extraction configuration disables reasoning explicitly.
    profile["extra_body"] = {**profile["extra_body"], "thinking": {"type": "disabled"}}
    path = workspace / "config/ai-providers.yml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"schema_version": 1, "default_profile": "deepseek",
                                   "profiles": {"deepseek": profile}}, allow_unicode=True), encoding="utf-8")
    reference = profile["api_key_ref"]
    environment = {
        "MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_DEFAULT_PROFILE": "deepseek",
        "MEMORY_OS_AI_CONFIG_FILE": str(path),
        "MEMORY_OS_AI_MAX_INPUT_CHARS": "20000",
        "MEMORY_OS_AI_KEYS__" + reference.upper(): resolved.api_key.get_secret_value(),
    }
    return path, environment


def check_runtime(runtime, evidence: Evidence) -> AcceptanceAPI:
    api = AcceptanceAPI(runtime.base_url, runtime.vault, evidence)
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if api.api("GET", "/openapi.json")["info"]["version"] != version:
        raise AcceptanceFailure("acceptance_image_version_mismatch")
    profiles = api.api("GET", "/api/v1/ai/profiles")
    if not profiles["enabled"] or not any(
            profile["id"] == "deepseek" and profile["configured"] for profile in profiles["items"]):
        raise AcceptanceFailure("acceptance_profile_not_ready")
    return api


def execute(mode: str, *, project_root: Path = PROJECT_ROOT, settings: Settings | None = None,
            runtime_types=None) -> tuple[int, Path]:
    if mode not in {"check", "run"}:
        raise ValueError("Select check or run explicitly.")
    settings = settings if settings is not None else Settings()
    profile, resolved = preflight(settings)
    workspace = new_workspace(project_root)
    secret_values = () if resolved is None else (resolved.api_key.get_secret_value(),)
    evidence = Evidence(workspace, profile, storage_fingerprint(project_root), secret_values)
    cases = load_cases(project_root)
    evidence.artifact("inputs.json", {"schema_version": 1, "cases": cases})
    evidence.quality_template(cases)
    if resolved is None:
        evidence.data.update(status="waiting_for_credentials", error_code=profile["error_code"],
                             actual_model_calls=0, formal_ai_changed=False,
                             formal_storage_unchanged=storage_fingerprint(project_root) == evidence.data["formal_before"],
                             finished_at=timestamp())
        evidence.save()
        return 2, workspace
    if mode == "check":
        evidence.data.update(status="ready_for_live_acceptance", actual_model_calls=0,
                             formal_ai_changed=False, finished_at=timestamp())
        evidence.save()
        return 0, workspace
    if runtime_types is None:
        from real_provider_runtime import DockerRuntime, LocalRuntime
        runtime_types = LocalRuntime, DockerRuntime
    profile_file, environment = prepare_profile(workspace, resolved)
    local = runtime_types[0](workspace, profile_file, environment)
    docker = runtime_types[1](workspace, profile_file, environment)
    guard = LiveBudgetGuard(workspace)
    try:
        guard.acquire()
    except Exception:
        evidence.data.update(status="review_required", error_code="live_budget_requires_review",
                             actual_model_calls=0, formal_ai_changed=False, finished_at=timestamp())
        evidence.save()
        return 1, workspace
    evidence.data["status"] = "running"
    evidence.save()
    failure = False
    try:
        local.migrate()
        local.start()
        check_case(check_runtime(local, evidence), cases[0])
        local.stop()
        docker.start()
        api = check_runtime(docker, evidence)
        check_persistence(api)
        for case in cases[1:]:
            check_case(api, case)
        docker.stop()
        docker.start()
        check_persistence(check_runtime(docker, evidence))
        evidence.data["status"] = "awaiting_quality_review"
    except Exception as error:
        failure = True
        evidence.data.update(status="failed", error_code=(str(error) if isinstance(error, AcceptanceFailure)
                                                           else "acceptance_workflow_failed"))
    finally:
        for runtime in (local, docker):
            try:
                runtime.stop()
            except Exception:
                failure = True
                evidence.data.update(status="cleanup_failed", error_code="acceptance_cleanup_failed")
        try:
            guard.release()
        except Exception:
            failure = True
            evidence.data.update(status="cleanup_failed", error_code="acceptance_budget_lock_changed")
        unchanged = storage_fingerprint(project_root) == evidence.data["formal_before"]
        if not unchanged:
            failure = True
            evidence.data.update(status="failed", error_code="formal_storage_changed")
        evidence.data.update(formal_storage_unchanged=unchanged, formal_ai_changed=False,
                             reserved_model_calls=len(evidence.data["attempts"]), finished_at=timestamp())
        evidence.save()
    return (1 if failure else 0), workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Check readiness without calls (default).")
    mode.add_argument("--run", action="store_true", help="Execute up to three live calls, with no retries.")
    args = parser.parse_args(argv)
    try:
        status, workspace = execute("run" if args.run else "check")
    except Exception as error:
        print(f"Acceptance preparation failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Acceptance evidence: {workspace}")
    print("Formal AI configuration was not changed; quality review is a separate step.")
    if status == 2:
        print("DeepSeek credentials/configuration are missing. No real model calls were sent.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
