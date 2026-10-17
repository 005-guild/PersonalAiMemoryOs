"""Shared local/container checks for four model protocols and explicit draft adoption."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

import yaml

from mock_model_server import EVIDENCE, SOURCE_TEXT
from verification_support import PROJECT_ROOT, eventually, note_path

PROTOCOLS = ("openai_chat", "openai_responses", "anthropic_messages", "gemini_generate_content")


def write_profiles(path: Path, base_url: str) -> None:
    """Write only verification profiles; never read a user's model configuration."""
    value = {
        "schema_version": 1,
        "default_profile": "openai_chat",
        "profiles": {
            protocol: {
                "label": f"Isolated {protocol}", "enabled": True, "protocol": protocol,
                "base_url": base_url, "model": "mock-model", "api_key_ref": "verification",
                "max_output_tokens": 4096, "timeout_seconds": 15,
                "response_format": "json_object" if protocol == "openai_chat" else "prompt",
                **({"extra_body": {"thinking": {"type": "disabled"}}} if protocol == "openai_chat" else {}),
            }
            for protocol in PROTOCOLS
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


class HttpApp:
    def __init__(self, base_url: str, vault: Path) -> None:
        self.base_url = base_url.rstrip("/")
        self.vault = vault

    def api(self, method: str, path: str, body: dict | None = None):
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(self.base_url + path, data=payload,
                          headers={"Content-Type": "application/json"}, method=method)
        with build_opener(ProxyHandler({})).open(request, timeout=100) as response:
            content = response.read()
            return json.loads(content) if content else None

    def note(self, note_id: str) -> dict:
        return self.api("GET", f"/api/v1/knowledge/{note_id}")


def vault_snapshot(vault: Path) -> dict[str, str]:
    return {str(path.relative_to(vault)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in vault.rglob("*") if path.is_file()}


def check_processing(app) -> dict:
    print("Checking four isolated model protocols, preview, adoption and Markdown edits...", flush=True)
    profiles = app.api("GET", "/api/v1/ai/profiles")
    assert profiles["enabled"] is True
    assert profiles["default_profile"] == "openai_chat"
    indexed = {item["id"]: item for item in profiles["items"]}
    for protocol in PROTOCOLS:
        assert indexed[protocol]["configured"] and indexed[protocol]["protocol"] == protocol
    assert "verification-only-key" not in json.dumps(profiles)
    state = {"runs": [], "initial_knowledge": app.api("GET", "/api/v1/knowledge?include_deleted=true")["total"]}
    for protocol in PROTOCOLS:
        source = app.api("POST", "/api/v1/sources", {
            "title": f"Synthetic model acceptance {protocol}", "content": SOURCE_TEXT,
            "source_type": "manual",
        })
        knowledge_before = app.api("GET", "/api/v1/knowledge?include_deleted=true")
        files_before = vault_snapshot(app.vault)
        run = app.api("POST", "/api/v1/processing/runs", {
            "source_id": source["id"], "expected_source_version": source["version"], "profile_id": protocol,
        })
        assert run["status"] == "ready" and run["profile_id"] == protocol
        assert run["source_stale"] is False and run["result"]["opinions"][0]["evidence"] == EVIDENCE
        details = app.api("GET", f"/api/v1/processing/runs/{run['id']}")
        assert details["proposal"] and details["result"] == run["result"]
        assert app.api("GET", "/api/v1/knowledge?include_deleted=true") == knowledge_before
        assert vault_snapshot(app.vault) == files_before, "Generating/previewing a draft modified vault files"
        adopted = app.api("POST", f"/api/v1/processing/runs/{run['id']}/adopt", {"expected_version": run["version"]})
        assert adopted["already_adopted"] is False and adopted["run"]["status"] == "adopted"
        note = adopted["knowledge"]
        assert note["source_id"] == source["id"] and EVIDENCE in note["body"]
        repeated = app.api("POST", f"/api/v1/processing/runs/{run['id']}/adopt", {"expected_version": run["version"]})
        assert repeated["already_adopted"] is True and repeated["knowledge"]["id"] == note["id"]
        assert app.api("GET", "/api/v1/knowledge?include_deleted=true")["total"] == knowledge_before["total"] + 1
        path = eventually(lambda: note_path(app.vault, note["id"]))
        eventually(lambda: app.note(note["id"])["sync_status"] == "synced")
        marker = f"Externally edited adopted note: {protocol}."
        path.write_text(path.read_text(encoding="utf-8") + "\n" + marker + "\n", encoding="utf-8")
        eventually(lambda: marker in app.note(note["id"])["body"])
        state["runs"].append({"id": run["id"], "version": run["version"], "knowledge_id": note["id"], "marker": marker})
    print("Four protocol generation/adoption/export/edit checks passed.", flush=True)
    return state


def check_processing_persistence(app, state: dict) -> None:
    print("Checking generated drafts and one-time adoption after restart...", flush=True)
    before = app.api("GET", "/api/v1/knowledge?include_deleted=true")["total"]
    for previous in state["runs"]:
        run = app.api("GET", f"/api/v1/processing/runs/{previous['id']}")
        assert run["status"] == "adopted" and run["adopted_knowledge_id"] == previous["knowledge_id"]
        assert previous["marker"] in app.note(previous["knowledge_id"])["body"]
        repeated = app.api("POST", f"/api/v1/processing/runs/{previous['id']}/adopt", {"expected_version": previous["version"]})
        assert repeated["already_adopted"] is True and repeated["knowledge"]["id"] == previous["knowledge_id"]
    assert app.api("GET", "/api/v1/knowledge?include_deleted=true")["total"] == before
    print("Processing persistence and repeat-adoption checks passed.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--phase", choices=("generate", "persist"), required=True)
    args = parser.parse_args()
    cache = (PROJECT_ROOT / ".cache").resolve()
    if not args.vault.resolve().is_relative_to(cache) or not args.state.resolve().is_relative_to(cache):
        raise ValueError("Acceptance storage must remain within the project cache")
    app = HttpApp(args.base_url, args.vault)
    if args.phase == "generate":
        args.state.write_text(json.dumps(check_processing(app), ensure_ascii=False), encoding="utf-8")
    else:
        check_processing_persistence(app, json.loads(args.state.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
