"""Exercise source grouping/pagination in an isolated real portable EXE."""

from __future__ import annotations

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
from source_groups_workflow import GROUPS, assert_source_storage, seed_sources, verify_source_groups
from v05_acceptance import storage_fingerprint
from v06_acceptance import browser_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=PROJECT_ROOT / f"dist/PersonalAiMemoryOs-{PROJECT_VERSION}")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Frozen EXE acceptance requires Windows.")
    bundle = args.bundle.resolve()
    if not (bundle / "PersonalAiMemoryOs.exe").is_file():
        parser.error("The selected frozen bundle is missing.")
    if any((bundle / name).exists() for name in (".env", "data", "knowledge", "logs", "config")):
        parser.error("Never copy an installation containing runtime/private data.")
    evidence = PROJECT_ROOT / ".cache/source-groups-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    portable = evidence / "分页 分组便携验收"
    shutil.copytree(bundle, portable)
    formal_before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0004", "real_model_calls": 0,
              "formal_before": formal_before, "evidence": str(evidence),
              "bundle": str(bundle), "private_dotenv_read": False,
              "executable_sha256": hashlib.sha256((bundle / "PersonalAiMemoryOs.exe").read_bytes()).hexdigest()}
    app = FrozenDesktop(portable, evidence)
    print(f"Source-group EXE evidence: {evidence}", flush=True)
    try:
        from playwright.sync_api import sync_playwright
        with browser_environment(evidence / "browser-tmp"), sync_playwright() as playwright:
            app.start()
            assert app.request("GET", "/api/v1/ai/profiles")["enabled"] is False
            assert app.request("GET", "/api/v1/rag/index/status")["enabled"] is False
            records, shared = seed_sources(app)
            browser, page = attach_window(playwright, app)
            report["workflow"] = verify_source_groups(browser, page, app, evidence, records, shared)
            report["storage"] = assert_source_storage(portable / "data/memory.db", records)
            app.request_close()
            app.wait_closed()
            app.start()
            assert app.request("GET", GROUPS + "?limit=100")["total"] == 46
            report["after_restart"] = assert_source_storage(portable / "data/memory.db", records)
            app.request_close()
            app.wait_closed()
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        report["check_stack"] = [{"file": item.filename, "line": item.lineno, "function": item.name}
                                 for item in traceback.extract_tb(error.__traceback__)]
        # All fixture text is authored here; no original article content is copied.
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Source-group acceptance failed: {error}", file=sys.stderr, flush=True)
    finally:
        app.stop()
        report["formal_storage_unchanged"] = formal_before == storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(evidence / "report.json")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
