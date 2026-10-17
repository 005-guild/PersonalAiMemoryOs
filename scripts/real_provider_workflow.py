"""Live HTTP workflow; only one guarded function can request model generation."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from real_provider_report import Evidence
from verification_support import eventually, note_path


class AcceptanceFailure(RuntimeError):
    """Public error codes without upstream response bodies or credentials."""


class AcceptanceAPI:
    def __init__(self, base_url: str, vault: Path, evidence: Evidence):
        self.base_url, self.vault, self.evidence = base_url.rstrip("/"), vault, evidence
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        # Generations must go through generate_once(), which persists the budget.
        if method.upper() == "POST" and path.split("?", 1)[0].rstrip("/") == "/api/v1/processing/runs":
            raise AcceptanceFailure("unguarded_generation")
        return self._request(method, path, body)

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(self.base_url + path, data=payload, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=110) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                try:
                    value = json.loads(error.read())
                    return error.code, value if isinstance(value, dict) else {}
                except (ValueError, UnicodeError):
                    return error.code, {}
        except Exception:
            raise AcceptanceFailure("acceptance_http_failure") from None

    def api(self, method: str, path: str, body: dict | None = None) -> dict:
        status, value = self.request(method, path, body)
        if not 200 <= status < 300:
            raise AcceptanceFailure("acceptance_api_failure")
        return value

    def generate_once(self, case: dict, source: dict) -> dict:
        self.evidence.reserve(case["id"], case["environment"], source["id"])
        status, value = self._request("POST", "/api/v1/processing/runs", {
            "source_id": source["id"], "expected_source_version": source["version"],
            "profile_id": "deepseek",
        })
        self.evidence.generation_result(status, value)
        if status != 201 or value.get("status") != "ready":
            raise AcceptanceFailure("real_generation_failed")
        return value


def vault_fingerprint(vault: Path) -> dict[str, str]:
    import hashlib
    return {p.relative_to(vault).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in vault.rglob("*") if p.is_file()}


def check_case(api: AcceptanceAPI, case: dict) -> dict:
    source = api.api("POST", "/api/v1/sources", {
        "title": case["title"], "source_type": "manual", "content": case["content"],
    })
    before = api.api("GET", "/api/v1/knowledge?include_deleted=true")
    files = vault_fingerprint(api.vault)
    run = api.generate_once(case, source)
    preview = api.api("GET", f"/api/v1/processing/runs/{run['id']}")
    assert preview["result"] == run["result"] and not preview["source_stale"]
    assert api.api("GET", "/api/v1/knowledge?include_deleted=true") == before
    assert vault_fingerprint(api.vault) == files
    # Only generated, locally schema-validated content is persisted in evidence.
    api.evidence.artifact(case["id"] + "-draft.json", preview)
    adopted = api.api("POST", f"/api/v1/processing/runs/{run['id']}/adopt", {"expected_version": run["version"]})
    assert not adopted["already_adopted"]
    note_id = adopted["knowledge"]["id"]
    retry = api.api("POST", f"/api/v1/processing/runs/{run['id']}/adopt", {"expected_version": run["version"]})
    assert retry["already_adopted"] and retry["knowledge"]["id"] == note_id
    assert api.api("GET", "/api/v1/knowledge?include_deleted=true")["total"] == before["total"] + 1
    path = eventually(lambda: note_path(api.vault, note_id))
    eventually(lambda: api.api("GET", f"/api/v1/knowledge/{note_id}")["sync_status"] == "synced")
    marker = f"真实联调隔离编辑标记：{case['id']}"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + marker + "\n", encoding="utf-8")
    eventually(lambda: marker in api.api("GET", f"/api/v1/knowledge/{note_id}")["body"])
    result = {"id": case["id"], "environment": case["environment"], "run_id": run["id"],
              "run_version": run["version"], "knowledge_id": note_id, "marker": marker,
              "workflow_passed": True, "quality_passed": None}
    api.evidence.data["cases"].append(result)
    api.evidence.save()
    return result


def check_persistence(api: AcceptanceAPI) -> None:
    before = api.api("GET", "/api/v1/knowledge?include_deleted=true")["total"]
    for case in api.evidence.data["cases"]:
        run = api.api("GET", f"/api/v1/processing/runs/{case['run_id']}")
        assert run["status"] == "adopted" and run["adopted_knowledge_id"] == case["knowledge_id"]
        note = api.api("GET", f"/api/v1/knowledge/{case['knowledge_id']}")
        assert case["marker"] in note["body"]
        retry = api.api("POST", f"/api/v1/processing/runs/{case['run_id']}/adopt", {"expected_version": case["run_version"]})
        assert retry["already_adopted"] and retry["knowledge"]["id"] == case["knowledge_id"]
    assert api.api("GET", "/api/v1/knowledge?include_deleted=true")["total"] == before
