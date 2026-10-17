"""Run sorting controls and global SQL order through a real frozen WebView2."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4

from verification_support import PROJECT_ROOT, PROJECT_VERSION

sys.path.insert(0, str(PROJECT_ROOT))

from desktop_verification_support import FrozenDesktop, attach_window
from source_sorting_fixture import check_sort_api, seed_sorting, source_snapshot
from source_sorting_workflow import assert_sorted_page, sorting_in_browser
from v05_acceptance import storage_fingerprint
from v06_acceptance import browser_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=PROJECT_ROOT / f"dist/PersonalAiMemoryOs-{PROJECT_VERSION}")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("The actual Windows EXE is required.")
    bundle = args.bundle.resolve()
    if not (bundle / "PersonalAiMemoryOs.exe").is_file():
        parser.error("The selected frozen bundle is missing.")
    if any((bundle / name).exists() for name in (".env", "data", "knowledge", "config", "logs")):
        parser.error("Do not copy personal/runtime data into acceptance.")
    evidence = PROJECT_ROOT / ".cache/source-sorting-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    runtime = evidence / "排序 便携隔离副本"
    shutil.copytree(bundle, runtime)
    before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0004", "real_model_calls": 0,
              "formal_before": before, "evidence": str(evidence), "private_dotenv_read": False,
              "executable_sha256": hashlib.sha256((bundle / "PersonalAiMemoryOs.exe").read_bytes()).hexdigest()}
    app = FrozenDesktop(runtime, evidence)
    database = runtime / "data/memory.db"
    print(f"Source-sorting EXE evidence: {evidence}", flush=True)
    try:
        from playwright.sync_api import sync_playwright
        with browser_environment(evidence / "browser-tmp"), sync_playwright() as playwright:
            app.start()
            assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
            assert app.request("GET", "/api/v1/ai/profiles")["enabled"] is False
            assert app.request("GET", "/api/v1/rag/index/status")["enabled"] is False
            records = seed_sorting(app, database)
            initial_sources = source_snapshot(database)
            report["api_order"] = check_sort_api(app, records)
            browser, page = attach_window(playwright, app)
            report["browser"] = sorting_in_browser(page, app, records, evidence)
            assert source_snapshot(database) == initial_sources
            app.request_close()
            app.wait_closed()
            app.start()
            assert source_snapshot(database) == initial_sources
            report["api_after_restart"] = check_sort_api(app, records)
            browser, page = attach_window(playwright, app)
            page.goto(app.url + "/" + report["browser"]["final_hash"])
            assert_sorted_page(page, records, "source_count", "desc", number=2)
            page.screenshot(path=str(evidence / "sorting-after-restart.png"), full_page=True)
            app.request_close()
            app.wait_closed()
            assert source_snapshot(database) == initial_sources
            report.update(source_snapshot_sha256=initial_sources, sources_unchanged_after_seed=True,
                          sources=67, active_sources=66, groups=27, restart_persistence=True, status="passed")
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Source-sorting acceptance failed: {error}", file=sys.stderr, flush=True)
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
