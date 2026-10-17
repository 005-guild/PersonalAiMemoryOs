"""Repeatable Chromium UI checks using explicitly synthetic, intercepted APIs."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Thread
import traceback
from uuid import uuid4

from playwright.sync_api import sync_playwright

from ui_patch_fixtures import PatchAPI
from ui_patch_search_checks import check_search_controls
from ui_patch_selection_checks import (
    check_filter_and_loading, check_last_page, check_network_stop,
    check_selection_and_cancel, check_stale_partial_delete,
)
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headed", action="store_true", help="Show the development Chromium window")
    args = parser.parse_args()
    evidence = PROJECT_ROOT / ".cache/ui-patch-validation" / uuid4().hex
    evidence.mkdir(parents=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".cache/playwright"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), AssetHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {"api_mode": "synthetic browser-route interception; no database/backend/provider",
              "real_model_calls": 0, "formal_data_accessed": False, "cases": {}}
    cases = [
        ("selection_cancel_deleted_keyboard", PatchAPI(5, deleted=(1,)), check_selection_and_cancel, "/knowledge"),
        ("filter_paging_loading", PatchAPI(25), check_filter_and_loading, "/knowledge"),
        ("stale_partial_delete", PatchAPI(3), check_stale_partial_delete, "/knowledge"),
        ("network_unknown_result", PatchAPI(3), check_network_stop, "/knowledge"),
        ("last_page_fallback", PatchAPI(21), check_last_page, "/knowledge"),
        ("search_controls", PatchAPI(0), check_search_controls, "/search"),
    ]
    try:
        with browser_environment(evidence / "tmp"), sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed, args=["--no-proxy-server"],
                                                 downloads_path=str(evidence / "downloads"))
            try:
                for name, api, check, route in cases:
                    folder = evidence / name
                    folder.mkdir()
                    context = browser.new_context(locale="zh-CN", service_workers="block",
                                                  viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    context.route("**/api/**", api.handle)
                    context.route("**/health", api.handle)
                    try:
                        page.goto(f"http://127.0.0.1:{server.server_port}/#" + route)
                        state = check(page, api, folder)
                        assert not errors, errors
                        report["cases"][name] = {**state, "page_errors": errors}
                        print(f"{name}: passed", flush=True)
                    except Exception:
                        page.screenshot(path=str(folder / "failure.png"), full_page=True, animations="disabled")
                        (folder / "failure.html").write_text(page.content(), encoding="utf-8")
                        report["cases"][name] = {"status": "failed", "page_errors": errors}
                        raise
                    finally:
                        (folder / "requests.json").write_text(json.dumps(api.calls, ensure_ascii=False, indent=2), encoding="utf-8")
                        context.close()
            finally:
                browser.close()
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"UI patch verification failed: {error}", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(evidence / "report.json")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
