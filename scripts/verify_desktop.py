"""Validate the actual frozen Windows EXE using its real WebView2 window."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import traceback
from uuid import uuid4

from desktop_browser_workflow import frozen_workflow, navigate
from desktop_lifecycle_workflow import check_inflight_close
from desktop_verification_support import FrozenDesktop, attach_window, check_invalid_configuration
from v05_acceptance import storage_fingerprint
from v06_acceptance import browser_environment
from verification_support import PROJECT_ROOT, PROJECT_VERSION, eventually


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=PROJECT_ROOT / "dist/PersonalAiMemoryOs")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Frozen Windows EXE acceptance requires Windows.")
    bundle = args.bundle.resolve()
    if not (bundle / "PersonalAiMemoryOs.exe").is_file():
        parser.error("Build the desktop bundle first; --bundle must contain PersonalAiMemoryOs.exe.")
    if any((bundle / name).exists() for name in (".env", "data/memory.db", "knowledge/.memory-os-vault")):
        parser.error("The distributable is not pristine; do not package personal/runtime data.")
    binary = (bundle / "PersonalAiMemoryOs.exe").read_bytes()
    pe_offset = int.from_bytes(binary[60:64], "little")
    if binary[:2] != b"MZ" or int.from_bytes(binary[pe_offset + 92:pe_offset + 94], "little") != 2:
        parser.error("The executable is not a Windows GUI PE binary; double-click must not open a console.")
    evidence = PROJECT_ROOT / ".cache/desktop-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    portable = evidence / "中文 空格便携目录"
    shutil.copytree(bundle, portable)
    before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0005", "real_model_calls": 0,
              "formal_before": before, "clean_second_pc_tested": False,
              "child_path": "System32 only; no Python/uv/Docker", "evidence": str(evidence),
              "bundle_directory": str(bundle),
              "pe_subsystem": "Windows GUI (2)",
              "executable_sha256": hashlib.sha256(binary).hexdigest()}
    app = FrozenDesktop(portable, evidence)
    print(f"Desktop evidence: {evidence}", flush=True)
    try:
        from playwright.sync_api import expect, sync_playwright
        with browser_environment(evidence / "driver-tmp"), sync_playwright() as playwright:
            app.start()
            report["workflow"] = frozen_workflow(playwright, app, evidence)
            app.start()
            browser, page = attach_window(playwright, app)
            navigate(page, app, "/knowledge/" + report["workflow"]["knowledge_id"])
            expect(page.get_by_test_id("knowledge-body")).to_have_value(report["workflow"]["body"])
            app.request_close()
            app.wait_closed()
            # Rename the entire independent bundle, never a formal project path.
            relocated = evidence / "移动后 中文便携目录"
            assert portable.resolve().is_relative_to(evidence.resolve())
            eventually(lambda: portable.rename(relocated), timeout=20)
            app = FrozenDesktop(relocated, evidence)
            app.start()
            browser, page = attach_window(playwright, app)
            navigate(page, app, "/knowledge/" + report["workflow"]["knowledge_id"])
            expect(page.get_by_test_id("knowledge-body")).to_have_value(report["workflow"]["body"])
            assert app.request("GET", "/api/v1/sources")["total"] == 2
            page.screenshot(path=str(evidence / "desktop-relocated-restart.png"), full_page=True)
            app.request_close()
            app.wait_closed()
            with sqlite3.connect(relocated / "data/memory.db") as database:
                assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert database.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005"
            report["workflow"]["passed"] += ["restart_persistence", "whole_directory_relocation", "sqlite_integrity"]
            report["inflight_close"] = check_inflight_close(playwright, relocated, evidence,
                                                            report["workflow"]["source_id"])
        report["invalid_configuration"] = check_invalid_configuration(relocated, evidence)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Desktop acceptance failed: {error}", file=sys.stderr, flush=True)
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
