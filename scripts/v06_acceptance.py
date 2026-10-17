"""Real Chromium acceptance against isolated local/Docker workspaces and Qdrant."""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback
from uuid import uuid4

from verification_support import PROJECT_ROOT, PROJECT_VERSION, eventually
from v05_acceptance import QDRANT_IMAGE, Runtime, json_file, storage_fingerprint
from v05_workflow import indexed
from v06_browser_workflow import run_browser_workflow


@contextmanager
def browser_environment(directory: Path):
    """Chromium profiles, downloads and driver temporaries remain project-local."""
    directory.mkdir(parents=True, exist_ok=True)
    previous = {name: os.environ.get(name) for name in ("TEMP", "TMP", "TMPDIR")}
    try:
        os.environ.update({name: str(directory) for name in previous})
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "docker", "all"], default="all")
    parser.add_argument("--image", default="memory-os-v06-validation:latest")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    browser_path = (PROJECT_ROOT / ".cache/playwright").resolve()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_path)
    from playwright.sync_api import sync_playwright

    cache = (PROJECT_ROOT / ".cache/v06-validation").resolve()
    if not cache.is_relative_to(PROJECT_ROOT.resolve()):
        raise RuntimeError("Acceptance storage must remain in the current project")
    cache.mkdir(parents=True, exist_ok=True)
    workspace = cache / uuid4().hex
    workspace.mkdir()
    before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0004", "real_model_calls": 0,
              "qdrant_image": QDRANT_IMAGE, "real_quality": "pending", "modes": {},
              "formal_before": before}
    print(f"Evidence: {workspace}", flush=True)
    helper = Runtime(workspace / "setup", "local", args.image)
    try:
        if not args.skip_build:
            helper.command(["docker", "build", "-t", args.image, "."], timeout=600)
        helper.command(["docker", "image", "inspect", QDRANT_IMAGE])
        with browser_environment(workspace / "browser-tmp"), sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-proxy-server"],
                                                   downloads_path=str(workspace / "downloads"))
            try:
                for mode in (["local", "docker"] if args.mode == "all" else [args.mode]):
                    runtime = Runtime(workspace / f"{mode}-{uuid4().hex[:12]}", mode, args.image,
                                      mock_script=PROJECT_ROOT / "scripts/v06_mock_server.py")
                    try:
                        app = runtime.start()
                        state = run_browser_workflow(browser, app, runtime.workspace)
                        app = runtime.restart()
                        eventually(lambda: app.note(state["knowledge_id"])["body"] == state["body"])
                        indexed(app, state["knowledge_id"])
                        context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                                      service_workers="block")
                        page = context.new_page()
                        page.goto(app.base_url + "/#/knowledge/" + state["knowledge_id"])
                        page.get_by_test_id("knowledge-title").wait_for()
                        page.screenshot(path=str(runtime.workspace / "restart.png"), full_page=True, animations="disabled")
                        context.close()
                        with closing(sqlite3.connect(runtime.database)) as database:
                            assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                            assert database.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0004"
                        report["modes"][mode] = {"status": "passed", "evidence": str(runtime.workspace),
                                                 "workflow": state}
                        print(f"{mode}: passed", flush=True)
                    finally:
                        runtime.stop()
            finally:
                browser.close()
        report["status"] = "engineering_passed"
    except Exception as error:
        report["status"], report["error_type"] = "failed", type(error).__name__
        (workspace / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Verification failed: {error}", file=sys.stderr, flush=True)
    finally:
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        json_file(workspace / "report.json", report)
    return 0 if report["status"] == "engineering_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
