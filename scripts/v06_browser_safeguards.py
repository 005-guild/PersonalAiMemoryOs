"""Focused browser checks for retained data, explicit retry and conflict choices."""

import json

from playwright.sync_api import expect

from verification_support import eventually, note_path
from v05_workflow import indexed


def confirm(page, label="确认"):
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=label, exact=True).click()


def check_lifecycle(page, app, note_id, body):
    """Delete, restore, repeat adoption, Markdown conflict and explicit rebuild."""
    page.get_by_test_id("entity-delete").click()
    confirm(page)
    eventually(lambda: app.note(note_id, include_deleted=True)["deleted_at"])
    eventually(lambda: note_path(app.vault, note_id) is None)
    assert not any(hit["knowledge_id"] == note_id for hit in app.search()["items"])
    page.goto(app.base_url + "/#/knowledge/" + note_id)
    page.get_by_test_id("entity-restore").click()
    eventually(lambda: app.note(note_id)["deleted_at"] is None)
    indexed(app, note_id)
    current = app.note(note_id)
    path = eventually(lambda: note_path(app.vault, note_id))
    eventually(lambda: app.note(note_id)["sync_status"] == "synced")
    # Both sides change from a common baseline before the file's second observation.
    edited = app.request("PATCH", f"/api/v1/knowledge/{note_id}", {
        "expected_version": current["version"], "body": body + "\n数据库保留版本。\n"})
    path.write_text(path.read_text(encoding="utf-8") + "\nMarkdown 保留版本。\n", encoding="utf-8")
    conflicts = eventually(lambda: app.request("GET", "/api/v1/sync/conflicts")["items"])
    assert any(item["knowledge_id"] == note_id for item in conflicts)
    page.goto(app.base_url + "/#/system")
    page.get_by_test_id("conflict-open").first.click()
    page.get_by_test_id("conflict-choose-database").click()
    confirm(page, "使用所选版本")
    eventually(lambda: app.note(note_id)["sync_status"] == "synced")
    assert app.note(note_id)["body"] == edited["body"]
    indexed(app, note_id)
    expect(page.get_by_test_id("index-run")).to_be_enabled(timeout=15000)
    page.get_by_test_id("index-run").click()
    confirm(page, "继续执行")
    expect(page.get_by_test_id("index-rebuild")).to_be_enabled(timeout=20000)
    page.get_by_test_id("index-rebuild").click()
    confirm(page, "继续执行")
    indexed(app, note_id)
    return edited["body"]


def check_disabled_and_failures(page, app, source_id):
    """Use browser-only transport fixtures; do not alter service/provider settings."""
    registry = app.request("GET", "/api/v1/ai/profiles")
    disabled = {**registry, "enabled": False}
    profile_route = "**/api/v1/ai/profiles"
    page.route(profile_route, lambda route: route.fulfill(status=200, content_type="application/json",
                                                        body=json.dumps(disabled)))
    page.goto(app.base_url + "/#/processing?source_id=" + source_id)
    expect(page.get_by_test_id("processing-generate")).to_be_disabled()
    expect(page.get_by_text("AI 当前关闭。", exact=False)).to_be_visible()
    page.unroute(profile_route)

    for status, code in [(429, "busy"), (504, "model_timeout")]:
        attempts = []
        def reject(route):
            attempts.append(route.request.post_data)
            route.fulfill(status=status, content_type="application/json",
                          body=json.dumps({"detail": {"code": code}}))
        page.route("**/api/v1/processing/runs", reject)
        page.goto(app.base_url + "/#/processing?source_id=" + source_id + "&case=" + str(status))
        expect(page.get_by_test_id("processing-generate")).to_be_enabled()
        page.get_by_test_id("processing-generate").click()
        expect(page.get_by_text("未自动重试。", exact=False)).to_be_visible()
        assert len(attempts) == 1, "A failed generation was automatically submitted again"
        page.unroute("**/api/v1/processing/runs", reject)


def check_partial_import(page, app, input_path):
    """An HTTP 503 report remains reviewable and is never automatically resubmitted."""
    page.goto(app.base_url + "/#/imports")
    page.get_by_test_id("import-file").set_input_files(input_path)
    page.get_by_test_id("import-preview").click()
    expect(page.get_by_test_id("import-submit")).to_be_enabled()
    preview = app.request("POST", "/api/v1/imports/zhihu?dry_run=true",
                          json.loads(input_path.read_text(encoding="utf-8")))
    partial = {**preview, "dry_run": False, "processed": 1, "invalid": 0, "failed": 1,
               "items": preview["items"][:1]}
    attempts = []
    def fail(route):
        attempts.append(route.request.post_data_buffer)
        route.fulfill(status=503, content_type="application/json",
                      body=json.dumps({"detail": "synthetic_partial_commit", "report": partial}))
    page.route("**/api/v1/imports/zhihu?dry_run=false", fail)
    page.get_by_test_id("import-submit").click()
    expect(page.get_by_test_id("import-report")).to_contain_text("已处理 1/2 条")
    expect(page.get_by_text("未自动重试。若请求中断", exact=False)).to_be_visible()
    assert attempts == [input_path.read_bytes()]
    expect(page.get_by_test_id("import-submit")).to_be_disabled()
    page.unroute("**/api/v1/imports/zhihu?dry_run=false", fail)
