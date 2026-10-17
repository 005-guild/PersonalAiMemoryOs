"""Exercise editor races in Chromium with synthetic, fully intercepted APIs."""

from __future__ import annotations

from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from threading import Thread
import traceback
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "app/web"
SOURCE = "10000000-0000-4000-8000-000000000001"
DELETED_SOURCE = "10000000-0000-4000-8000-000000000002"
NOTE = "20000000-0000-4000-8000-000000000001"
DELETED_NOTE = "20000000-0000-4000-8000-000000000002"
CREATED_SOURCE = "10000000-0000-4000-8000-000000000003"
STAMP = "2026-10-17T00:00:00+00:00"


class AssetHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        relative = urlsplit(path).path
        if relative == "/":
            return str(WEB_ROOT / "index.html")
        if relative.startswith("/assets/"):
            target = (WEB_ROOT / relative.removeprefix("/assets/")).resolve()
            if target.is_relative_to(WEB_ROOT.resolve()):
                return str(target)
        return str(WEB_ROOT / "__not_published__")

    def log_message(self, format, *args):
        pass


def fixtures():
    common = {"version": 1, "created_at": STAMP, "updated_at": STAMP, "deleted_at": None}
    source = {**common, "id": SOURCE, "source_type": "manual", "title": "合成来源",
              "author": None, "url": None, "content": "纯浏览器测试资料"}
    note = {**common, "id": NOTE, "source_id": SOURCE, "title": "保留原文笔记",
            "body": "第一行\r\n第二行\r\n", "summary": "摘要", "category": "中文分类",
            "tags": ["tag,with,comma", "包含，中文逗号"], "concepts": ["C++, std"],
            "deleted": False, "sync_status": "pending"}
    return {
        "sources": {SOURCE: source, DELETED_SOURCE: {**source, "id": DELETED_SOURCE,
                    "title": "已删除来源", "version": 2, "deleted_at": STAMP}},
        "knowledge": {NOTE: note, DELETED_NOTE: {**note, "id": DELETED_NOTE,
                      "source_id": DELETED_SOURCE, "title": "待恢复笔记", "version": 2,
                      "deleted": True, "deleted_at": STAMP}},
    }


class BrowserAPI:
    def __init__(self):
        self.records, self.pending, self.calls = fixtures(), [], []

    @staticmethod
    def reply(route, data, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data, ensure_ascii=False))

    def handle(self, route):
        request = route.request
        path, method = urlsplit(request.url).path, request.method
        payload = request.post_data_json if method != "GET" else None
        self.calls.append({"method": method, "path": path, "body": payload})
        if method in {"POST", "PATCH"}:
            self.pending.append((route, method, path, payload))
            return
        if path == "/health":
            return self.reply(route, {"status": "ok", "database": "ok"})
        if path.startswith("/api/v1/ui/"):
            if path.endswith("/overview"):
                return self.reply(route, {"active_sources": 1, "active_knowledge": 1,
                                          "ready_drafts": 0, "open_conflicts": 0})
            return self.reply(route, {"items": [], "total": 0, "offset": 0, "limit": 20})
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[2] in self.records and parts[3] in self.records[parts[2]]:
            return self.reply(route, self.records[parts[2]][parts[3]])
        return self.reply(route, {"detail": "Unexpected browser fixture request"}, 404)

    def finish(self):
        route, method, path, payload = self.pending.pop(0)
        parts = path.strip("/").split("/")
        collection = parts[2]
        if len(parts) == 3:
            record = {**deepcopy(self.records["sources"][SOURCE]), **payload,
                      "id": CREATED_SOURCE, "version": 1}
        else:
            record = deepcopy(self.records[collection][parts[3]])
            record.update({key: value for key, value in payload.items() if key != "expected_version"})
            record["version"] += 1
            if path.endswith("/restore"):
                record.update(deleted=False, deleted_at=None)
        self.records[collection][record["id"]] = record
        self.reply(route, record, 201 if method == "POST" and len(parts) == 3 else 200)


def confirm(page, label="确认"):
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=label, exact=True).click()


def run_editor_safeguards(browser):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(AssetHandler, directory=WEB_ROOT))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context(service_workers="block")
    transport, errors, checks = BrowserAPI(), [], []
    context.route("**/api/**", transport.handle)
    context.route("**/health", transport.handle)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))

    def open_editor(identifier=NOTE, section="knowledge"):
        page.goto(f"{base_url}/#/{section}/{identifier}")
        expect(page.get_by_test_id(f"{'source' if section == 'sources' else section}-title")).to_be_visible()

    try:
        open_editor()
        page.get_by_test_id("knowledge-title").fill("只修改标题")
        page.get_by_test_id("knowledge-save").click()
        assert len(transport.pending) == 1
        payload = transport.pending[0][3]
        assert payload == {"title": "只修改标题", "expected_version": 1}, payload
        for testid in ("knowledge-title", "knowledge-body", "knowledge-tags", "knowledge-source"):
            expect(page.get_by_test_id(testid)).to_be_disabled()
        transport.finish()
        expect(page.get_by_test_id("knowledge-title")).to_have_value("只修改标题")
        expect(page.get_by_test_id("knowledge-title")).to_be_enabled()
        assert transport.records["knowledge"][NOTE]["body"] == "第一行\r\n第二行\r\n"
        assert transport.records["knowledge"][NOTE]["tags"] == ["tag,with,comma", "包含，中文逗号"]
        checks.extend(["patch_disables_editing", "unchanged_comma_tags_and_crlf_are_not_submitted"])

        open_editor("new", "sources")
        page.get_by_test_id("source-title").fill("新建时防止继续输入")
        page.get_by_test_id("source-content").fill("等待中的新建请求")
        page.get_by_test_id("source-save").click()
        assert len(transport.pending) == 1
        for testid in ("source-title", "source-content", "source-author"):
            expect(page.get_by_test_id(testid)).to_be_disabled()
        transport.finish()
        expect(page).to_have_url(re.compile(re.escape(f"{base_url}/#/sources/{CREATED_SOURCE}")))
        checks.append("post_disables_editing")

        open_editor()
        page.get_by_test_id("knowledge-title").fill("上一页面保存中")
        page.get_by_test_id("knowledge-save").click()
        assert len(transport.pending) == 1
        page.get_by_role("navigation").get_by_role("link", name="资料库", exact=True).click()
        confirm(page, "离开")
        expect(page.get_by_role("heading", name="原始资料", exact=True)).to_be_visible()
        page.get_by_role("navigation").get_by_role("link", name="知识笔记", exact=True).click()
        page.get_by_role("button", name="＋ 新建笔记", exact=True).click()
        page.get_by_test_id("knowledge-title").fill("新页面未保存输入")
        transport.finish()
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        assert page.url == f"{base_url}/#/knowledge/new"
        expect(page.get_by_test_id("knowledge-title")).to_have_value("新页面未保存输入")
        page.get_by_role("navigation").get_by_role("link", name="资料库", exact=True).click()
        confirm(page, "取消")
        assert page.url == f"{base_url}/#/knowledge/new"
        checks.append("late_save_preserves_next_editor_route_and_dirty_state")

        # Leave the unsaved page through its explicit guard, then open a deleted note.
        page.get_by_role("navigation").get_by_role("link", name="资料库", exact=True).click()
        confirm(page, "离开")
        open_editor(DELETED_NOTE)
        page.get_by_test_id("entity-restore").click()
        unlink = page.get_by_role("button", name="解除关联并恢复", exact=True)
        expect(unlink).to_be_visible()
        unlink.click()
        confirm(page)
        assert len(transport.pending) == 1
        assert transport.pending[0][3] == {"expected_version": 2, "source_id": None}
        unlink.evaluate("node => node.click()")
        expect(page.get_by_role("dialog")).to_have_count(0)
        assert len(transport.pending) == 1
        restore_calls = [call for call in transport.calls
                         if call["method"] == "POST" and call["path"].endswith("/restore")]
        assert len(restore_calls) == 1
        expect(page.get_by_test_id("knowledge-body")).to_be_disabled()
        transport.finish()
        expect(page.get_by_test_id("knowledge-title")).to_be_enabled()
        expect(page.get_by_test_id("knowledge-source")).to_be_enabled()
        assert transport.records["knowledge"][DELETED_NOTE]["source_id"] is None
        checks.append("deleted_source_unlink_restore_is_single_and_reenables_fields")
        assert not errors, errors
        return {"status": "passed", "checks": checks, "page_errors": errors,
                "api_calls": transport.calls, "real_model_calls": 0, "database_opened": False}
    finally:
        context.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    browser_temp = PROJECT_ROOT / ".cache/v06-editor-browser-tmp"
    browser_temp.mkdir(parents=True, exist_ok=True)
    variables = {"PLAYWRIGHT_BROWSERS_PATH": str(PROJECT_ROOT / ".cache/playwright"),
                 "TEMP": str(browser_temp), "TMP": str(browser_temp), "TMPDIR": str(browser_temp)}
    previous = {key: os.environ.get(key) for key in variables}
    os.environ.update(variables)
    report_path = PROJECT_ROOT / ".cache/v06-editor-review.json"
    report_path.parent.mkdir(exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-proxy-server"])
            try:
                report = run_editor_safeguards(browser)
            finally:
                browser.close()
    except Exception as error:
        report = {"status": "failed", "error": str(error), "traceback": traceback.format_exc()}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Editor safeguards: {report['status']} ({report_path})", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
