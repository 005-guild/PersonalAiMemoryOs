"""Validate AI settings using an actual isolated portable EXE and a never-called endpoint."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4

from verification_support import PROJECT_ROOT, PROJECT_VERSION, eventually

sys.path.insert(0, str(PROJECT_ROOT))

from ai_settings_verification import (
    business_snapshot, seed_business_records, secret_absent, unused_model_endpoint, verify_private_files,
)
from ai_settings_workflow import PROFILE_ID, save_settings_in_browser, verify_settings_after_restart
from desktop_verification_support import FrozenDesktop, attach_window
from v05_acceptance import storage_fingerprint
from v06_acceptance import browser_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=PROJECT_ROOT / f"dist/PersonalAiMemoryOs-{PROJECT_VERSION}")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    if os.name != "nt" or not (bundle / "PersonalAiMemoryOs.exe").is_file():
        parser.error("The actual Windows frozen bundle is required.")
    if any((bundle / name).exists() for name in (".env", "data", "knowledge", "config", "logs")):
        parser.error("Acceptance requires a pristine bundle without runtime or personal data.")
    evidence = PROJECT_ROOT / ".cache/ai-settings-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    runtime = evidence / "设置 隔离便携副本"
    shutil.copytree(bundle, runtime)
    before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0004", "evidence": str(evidence),
              "real_model_calls": 0, "private_dotenv_read": False, "formal_before": before,
              "executable_sha256": hashlib.sha256((bundle / "PersonalAiMemoryOs.exe").read_bytes()).hexdigest()}
    app = FrozenDesktop(runtime, evidence)
    database = runtime / "data/memory.db"
    # Synthetic and deliberately not written into reports, URLs or command arguments.
    secret = "synthetic-settings-only-" + uuid4().hex
    print(f"AI-settings EXE evidence: {evidence}", flush=True)
    try:
        from playwright.sync_api import sync_playwright
        with unused_model_endpoint() as (model_url, model_calls), browser_environment(evidence / "browser-tmp"), sync_playwright() as playwright:
            app.start()
            assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
            assert app.request("GET", "/api/v1/ai/profiles")["enabled"] is False
            assert app.request("GET", "/api/v1/rag/index/status")["enabled"] is False
            snapshot = app.request("GET", "/api/v1/settings/ai")
            assert snapshot["editable"] is True
            initial_profiles = {profile["id"]: profile for profile in snapshot["profiles"]}
            source_id, note_id = seed_business_records(app)
            eventually(lambda: app.request("GET", f"/api/v1/knowledge/{note_id}")["sync_status"] == "synced", timeout=30)
            business_before = business_snapshot(database)
            browser, page = attach_window(playwright, app)
            report["save"] = save_settings_in_browser(page, app, model_url, secret, evidence)
            saved = app.request("GET", "/api/v1/settings/ai")
            secret_absent(saved, secret)
            assert {profile["id"]: profile for profile in saved["profiles"] if profile["id"] != PROFILE_ID} == initial_profiles
            report["files"] = verify_private_files(runtime, secret, PROFILE_ID, model_url)
            assert business_snapshot(database) == business_before
            assert not model_calls
            app.request_close()
            app.wait_closed()
            app.start()
            browser, page = attach_window(playwright, app)
            report["restart"] = verify_settings_after_restart(page, app, secret, evidence)
            assert app.request("GET", f"/api/v1/sources/{source_id}")["version"] == 1
            assert app.request("GET", f"/api/v1/knowledge/{note_id}")["version"] == 1
            assert business_snapshot(database) == business_before
            assert not model_calls
            app.request_close()
            app.wait_closed()
            report["files_after_restart"] = verify_private_files(runtime, secret, PROFILE_ID, model_url)
            report.update(business_snapshot_sha256=business_before, business_records_unchanged=True,
                          original_profiles_preserved=True, endpoint_requests=len(model_calls), status="passed")
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error).replace(secret, "[synthetic-key-redacted]"))
        (evidence / "failure.txt").write_text(traceback.format_exc().replace(secret, "[synthetic-key-redacted]"), encoding="utf-8")
        print(f"AI-settings acceptance failed: {report['error']}", file=sys.stderr, flush=True)
    finally:
        app.stop()
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(evidence / "report.json")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
