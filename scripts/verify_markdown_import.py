"""Read-only real 571-file Markdown acceptance against local/portable runtimes."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4

from verification_support import PROJECT_ROOT, PROJECT_VERSION

sys.path.insert(0, str(PROJECT_ROOT))

from desktop_verification_support import FrozenDesktop, attach_window
from markdown_import_support import ExportCorpus, LocalMarkdownRuntime, verify_storage
from markdown_import_workflow import check_disabled_and_counts, import_in_browser
from v05_acceptance import storage_fingerprint
from v06_acceptance import browser_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "desktop"], default="local")
    parser.add_argument("--bundle", type=Path, default=PROJECT_ROOT / f"dist/PersonalAiMemoryOs-{PROJECT_VERSION}")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "\u77e5\u4e4e")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    original = args.input_dir.resolve()
    if not original.is_dir() or not original.is_relative_to(PROJECT_ROOT):
        parser.error("The read-only export directory must exist inside the project.")
    if args.mode == "desktop" and os.name != "nt":
        parser.error("Desktop acceptance requires Windows and the actual frozen EXE.")
    evidence = PROJECT_ROOT / ".cache/markdown-import-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    before = storage_fingerprint()
    corpus = ExportCorpus(original)
    report = {"version": PROJECT_VERSION, "schema": "0004", "mode": args.mode, "evidence": str(evidence),
              "input": corpus.summary(), "formal_before": before, "real_model_calls": 0,
              "private_dotenv_read": False, "source_only": True}
    app = None
    print(f"Markdown import evidence: {evidence}", flush=True)
    try:
        if args.mode == "desktop":
            bundle = args.bundle.resolve()
            if not (bundle / "PersonalAiMemoryOs.exe").is_file():
                raise RuntimeError("The selected frozen bundle is missing")
            if any((bundle / name).exists() for name in (".env", "data", "knowledge", "logs", "config")):
                raise RuntimeError("Never copy a portable installation containing runtime/private data")
            runtime = evidence / "portable-runtime"
            shutil.copytree(bundle, runtime)
            app = FrozenDesktop(runtime, evidence)
        else:
            runtime = evidence / "local-runtime"
            runtime.mkdir()
            app = LocalMarkdownRuntime(runtime)
        database = runtime / "data/memory.db"
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PROJECT_ROOT / ".cache/playwright")
        from playwright.sync_api import sync_playwright

        with browser_environment(evidence / "browser-tmp"), sync_playwright() as playwright:
            app.start()
            if args.mode == "desktop":
                browser, page = attach_window(playwright, app)
            else:
                browser = playwright.chromium.launch(args=["--no-proxy-server"], downloads_path=str(evidence / "downloads"))
                context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN", service_workers="block")
                page = context.new_page()
            created, report["browser"] = import_in_browser(browser, page, app, corpus, evidence, desktop=args.mode == "desktop")
            report["storage"] = verify_storage(database, corpus, created)
            app.stop()
            app.start()
            check_disabled_and_counts(app, 571)
            report["after_restart"] = verify_storage(database, corpus, created)
            if args.mode == "desktop":
                browser, page = attach_window(playwright, app)
            page.goto(app.url + "/#/")
            page.locator("#main h1").wait_for()
            page.screenshot(path=str(evidence / "restarted-overview.png"), full_page=True)
            app.stop()
            if args.mode == "local":
                browser.close()
        report["copied_export_images"] = corpus.check_image_copies(runtime)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["check_stack"] = [{"file": item.filename, "line": item.lineno, "function": item.name}
                                 for item in traceback.extract_tb(error.__traceback__)]
        # Exception values/response bodies are deliberately excluded from evidence.
        print(f"Markdown import acceptance failed: {type(error).__name__}", file=sys.stderr, flush=True)
    finally:
        if app:
            app.stop()
        report["original_files_unchanged"] = corpus.before == corpus.snapshot()
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["original_files_unchanged"] or not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(evidence / "report.json")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
