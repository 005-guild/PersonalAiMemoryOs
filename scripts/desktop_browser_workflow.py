"""Interact with the packaged app's actual embedded Edge/WebView2 page."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import subprocess

from playwright.sync_api import expect

from desktop_verification_support import attach_window
from verification_support import PROJECT_VERSION, eventually, note_path


def navigate(page, app, route):
    page.goto(app.url + "/#" + route)
    expect(page.locator("#main .loading")).to_have_count(0)


def confirm(page, label="确认"):
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=label, exact=True).click()


def observed_path(root, note_id):
    connection = sqlite3.connect(root / "data/memory.db")
    try:
        row = connection.execute("SELECT path FROM sync_states WHERE knowledge_id = ?", (note_id,)).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def frozen_workflow(playwright, app, evidence: Path):
    browser, page = attach_window(playwright, app)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.screenshot(path=str(evidence / "desktop-first-launch.png"), full_page=True)
    assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
    assert app.request("GET", "/api/v1/sources")["total"] == 0
    assert app.request("GET", "/api/v1/knowledge")["total"] == 0
    assert app.request("GET", "/api/v1/ai/profiles")["enabled"] is False
    assert app.request("GET", "/api/v1/rag/index/status")["enabled"] is False

    navigate(page, app, "/sources/new")
    page.get_by_test_id("source-title").fill("便携版中文资料")
    page.get_by_test_id("source-content").fill("索引减少查询扫描，但增加写入成本。\n这是离线验收资料。")
    with page.expect_response(lambda response: response.url.endswith("/api/v1/sources")
                              and response.request.method == "POST") as response:
        page.get_by_test_id("source-save").click()
    assert response.value.status == 201
    source = response.value.json()
    expect(page.get_by_test_id("entity-delete")).to_be_visible()
    page.get_by_test_id("source-title").fill("便携版编辑后的资料")
    page.get_by_test_id("source-save").click()
    eventually(lambda: app.request("GET", "/api/v1/sources/" + source["id"])["version"] == 2)
    expect(page.get_by_test_id("source-title")).to_have_value("便携版编辑后的资料")
    navigate(page, app, "/sources/" + source["id"])
    page.get_by_test_id("entity-delete").click()
    confirm(page)
    eventually(lambda: app.request("GET", "/api/v1/sources/" + source["id"] + "?include_deleted=true")["deleted_at"])
    navigate(page, app, "/sources/" + source["id"])
    page.get_by_test_id("entity-restore").click()
    eventually(lambda: app.request("GET", "/api/v1/sources/" + source["id"])["deleted_at"] is None)

    navigate(page, app, "/knowledge/new")
    page.get_by_test_id("knowledge-title").fill("便携知识笔记")
    body = "# 中文标题\n\n这是独立笔记。\n```python\nprint('hello')\n```\n"
    page.get_by_test_id("knowledge-body").fill(body)
    expect(page.get_by_test_id("markdown-preview")).to_contain_text("中文标题")
    with page.expect_response(lambda response: response.url.endswith("/api/v1/knowledge")
                              and response.request.method == "POST") as response:
        page.get_by_test_id("knowledge-save").click()
    assert response.value.status == 201
    note = response.value.json()
    note_id = note["id"]
    page.wait_for_url(re.compile(r"/#/$"))
    path = eventually(lambda: note_path(app.root / "knowledge", note_id))
    eventually(lambda: app.request("GET", "/api/v1/knowledge/" + note_id)["sync_status"] == "synced")

    # External edits and moves preserve the same stored UUID.
    path.write_text(path.read_text(encoding="utf-8") + "\n普通编辑器新增。\n", encoding="utf-8")
    eventually(lambda: "普通编辑器新增。" in app.request("GET", "/api/v1/knowledge/" + note_id)["body"])
    subdirectory = app.root / "knowledge/中文 子目录"
    subdirectory.mkdir()
    moved = subdirectory / "移动后的笔记.md"
    path.replace(moved)
    eventually(lambda: app.request("GET", "/api/v1/sync/status").get("errors", []) == [])
    # Two stable observations are needed before testing deletion.
    eventually(lambda: observed_path(app.root, note_id) == "中文 子目录/移动后的笔记.md")
    eventually(lambda: app.request("GET", "/api/v1/knowledge/" + note_id)["sync_status"] == "synced")

    navigate(page, app, "/knowledge/" + note_id)
    expect(page.get_by_test_id("knowledge-body")).to_have_value(re.compile("普通编辑器新增。"))
    page.get_by_test_id("entity-delete").click()
    confirm(page)
    eventually(lambda: app.request("GET", "/api/v1/knowledge/" + note_id + "?include_deleted=true")["deleted_at"])
    eventually(lambda: note_path(app.root / "knowledge", note_id) is None)
    navigate(page, app, "/knowledge/" + note_id)
    page.get_by_test_id("entity-restore").click()
    eventually(lambda: app.request("GET", "/api/v1/knowledge/" + note_id)["deleted_at"] is None)
    eventually(lambda: note_path(app.root / "knowledge", note_id))

    navigate(page, app, "/imports")
    input_path = evidence / "中文 离线导入.json"
    input_path.write_text(json.dumps({"schema_version": 1, "items": [{
        "url": "https://www.zhihu.com/question/602/answer/603",
        "title": "便携版导入资料", "content": "测试中文、换行\n和引号\"的原文保存。"
    }]}, ensure_ascii=False), encoding="utf-8")
    page.get_by_test_id("import-file").set_input_files(input_path)
    page.get_by_test_id("import-preview").click()
    expect(page.get_by_test_id("import-report")).to_contain_text("预计创建 1")
    assert app.request("GET", "/api/v1/sources")["total"] == 1
    page.get_by_test_id("import-submit").click()
    expect(page.get_by_test_id("import-report")).to_contain_text("已创建 1")
    downloads = app.root / "exports"
    downloads.mkdir(exist_ok=True)
    session = browser.new_browser_cdp_session()
    webview_version = session.send("Browser.getVersion")
    session.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads), "eventsEnabled": True})
    page.get_by_role("button", name="下载报告", exact=True).click()
    report_file = eventually(lambda: next((item for item in downloads.glob("*.json") if item.is_file()), None))
    assert json.loads(report_file.read_text(encoding="utf-8"))["created"] == 1
    assert app.request("GET", "/api/v1/knowledge")["total"] == 1

    # Duplicate double-click exits without another backend or vault identity.
    duplicate = subprocess.Popen([str(app.root / "PersonalAiMemoryOs.exe")], cwd=evidence,
                                 env=app.environment, creationflags=subprocess.CREATE_NO_WINDOW)
    assert duplicate.wait(timeout=15) == 0
    assert app.request("GET", "/health")["status"] == "ok"
    runtime = json.loads((app.root / ".cache/desktop/runtime.json").read_text(encoding="utf-8"))
    assert runtime["pid"] == app.process.pid and runtime["url"].rstrip("/") == app.url

    navigate(page, app, "/knowledge/" + note_id)
    final_body = app.request("GET", "/api/v1/knowledge/" + note_id)["body"]
    page.get_by_test_id("knowledge-body").fill(final_body + "\n未保存内容应保留到取消关窗。")
    app.request_close()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_role("dialog").get_by_role("button", name="取消", exact=True).click()
    assert app.process.poll() is None
    expect(page.get_by_test_id("knowledge-body")).to_have_value(re.compile("未保存内容应保留到取消关窗。"))
    page.screenshot(path=str(evidence / "desktop-unsaved-close-cancel.png"), full_page=True)
    app.request_close()
    confirm(page, "退出")
    app.wait_closed()
    assert not errors, errors
    return {"source_id": source["id"], "knowledge_id": note_id, "body": final_body,
            "passed": ["first_empty_launch", "native_webview2", "source_crud", "knowledge_crud",
                       "markdown_preview", "external_edit_move", "trash_restore", "json_file_selection",
                       "import_preview_commit", "report_download", "duplicate_activation",
                       "unsaved_close_cancel", "graceful_close", "port_released"],
            "page_errors": errors, "webview_version": webview_version}
