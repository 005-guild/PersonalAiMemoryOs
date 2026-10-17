"""Browser-level workflow and safeguards for synthetic v0.6 data only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect

from verification_support import PROJECT_VERSION, eventually, note_path
from v05_workflow import indexed
from v06_browser_safeguards import check_disabled_and_failures, check_lifecycle, check_partial_import

SOURCE_TEXT = "数据库索引可以减少查询扫描的数据量。索引也增加写入和存储成本。\n应根据实际查询验证索引效果。"


def confirm(page, label: str = "确认") -> None:
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=label, exact=True).click()


def navigate(page, app, route: str) -> None:
    page.goto(app.base_url + "/#" + route)
    expect(page.locator("#main .loading")).to_have_count(0)


def run_browser_workflow(browser, app, evidence: Path) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                  locale="zh-CN", service_workers="block")
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    errors, console, external = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console.append({"type": message.type, "text": message.text}))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost", None} else None)
    state = {}
    try:
        assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
        navigate(page, app, "/")
        expect(page.locator("#page-title")).to_have_text("概览")
        expect(page.locator("#main h1")).to_be_visible()
        for width in (1440, 1024, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            page.screenshot(path=str(evidence / f"overview-{width}.png"), full_page=True, animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Horizontal overflow at {width}"
        page.get_by_role("button", name="展开导航", exact=True).click()
        expect(page.get_by_role("navigation").get_by_role("link", name="资料库", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 1440, "height": 1000})

        # Create/edit via the actual form; Source stays out of Knowledge/RAG.
        navigate(page, app, "/sources/new")
        page.get_by_test_id("source-title").fill("浏览器验收资料")
        page.get_by_test_id("source-content").fill(SOURCE_TEXT)
        with page.expect_response(lambda response: response.url.endswith("/api/v1/sources")
                                  and response.request.method == "POST") as response:
            page.get_by_test_id("source-save").click()
        assert response.value.status == 201
        source = response.value.json()
        source_id = source["id"]
        expect(page).to_have_url(re.compile(re.escape(app.base_url + "/#/sources/" + source_id)))
        expect(page.get_by_test_id("entity-delete")).to_be_visible()

        # Retain local content on stale saves rather than overwriting newer input.
        page.get_by_test_id("source-title").fill("本地未保存的资料标题")
        server_source = app.request("PATCH", f"/api/v1/sources/{source_id}", {
            "expected_version": source["version"], "title": "另一窗口保存的资料标题"})
        with page.expect_response(lambda response: f"/api/v1/sources/{source_id}" in response.url
                                  and response.request.method == "PATCH") as response:
            page.get_by_test_id("source-save").click()
        assert response.value.status == 409
        expect(page.get_by_test_id("source-title")).to_have_value("本地未保存的资料标题")
        assert app.request("GET", f"/api/v1/sources/{source_id}")["title"] == server_source["title"]
        page.locator('#navigation a[href="#/knowledge"]').click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_role("dialog").get_by_role("button", name="取消", exact=True).click()
        expect(page.get_by_test_id("source-title")).to_have_value("本地未保存的资料标题")
        page.locator('#navigation a[href="#/imports"]').click()
        confirm(page, "离开")

        # One selected byte sequence is previewed and then committed, including invalid items.
        input_path = evidence / "browser-import.json"
        payload = {"schema_version": 1, "items": [
            {"url": "https://www.zhihu.com/question/761/answer/762", "title": "离线导入样例", "content": SOURCE_TEXT},
            {"url": "https://example.invalid/invalid", "title": "无效条目", "content": "不会导入"}]}
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        page.get_by_test_id("import-file").set_input_files(input_path)
        page.get_by_test_id("import-preview").click()
        expect(page.get_by_test_id("import-report")).to_contain_text("预计创建 1")
        assert app.request("GET", "/api/v1/sources")["total"] == 1
        page.get_by_test_id("import-submit").click()
        expect(page.get_by_test_id("import-report")).to_contain_text("已创建 1")
        expect(page.get_by_test_id("import-report")).to_contain_text("无效 1")
        with page.expect_download() as download:
            page.get_by_role("button", name="下载报告", exact=True).click()
        report_path = evidence / "downloaded-import-report.json"
        download.value.save_as(report_path)
        assert json.loads(report_path.read_text(encoding="utf-8"))["created"] == 1

        navigate(page, app, "/processing?source_id=" + source_id)
        expect(page.get_by_test_id("processing-generate")).to_be_enabled()
        before_notes = app.request("GET", "/api/v1/knowledge")["total"]
        with page.expect_response(lambda response: response.url.endswith("/api/v1/processing/runs")
                                  and response.request.method == "POST") as response:
            page.get_by_test_id("processing-generate").click()
        assert response.value.status == 201
        run = response.value.json()
        expect(page.get_by_test_id("processing-run-detail")).to_be_visible()
        assert app.request("GET", "/api/v1/knowledge")["total"] == before_notes
        page.get_by_test_id("processing-adopt").click()
        page.get_by_test_id("knowledge-title").wait_for()
        adopted = app.request("GET", "/api/v1/processing/runs/" + run["id"])
        note_id = adopted["adopted_knowledge_id"]
        note = app.note(note_id)
        assert note["source_id"] == source_id
        eventually(lambda: note_path(app.vault, note_id))

        # Safe preview: scripts/raw HTML, remote media and javascript links never execute/load.
        body = note["body"] + "\n## 浏览器新增\n```python\nprint('中文')\n```\n" + (
            '<script>window.__unsafePreview=1</script>\n'
            '<img src="https://external.invalid/pixel" onerror="window.__unsafePreview=2">\n'
            '[危险链接](javascript:alert(1))\n![外部图片](https://external.invalid/image.png)\n')
        page.get_by_test_id("knowledge-body").fill("长" * 100001)
        expect(page.get_by_test_id("markdown-preview")).to_contain_text("已暂停预览")
        assert len(page.get_by_test_id("knowledge-body").input_value()) == 100001
        page.get_by_test_id("knowledge-body").fill(body)
        page.get_by_test_id("knowledge-body").dispatch_event("input")
        assert page.evaluate("window.__unsafePreview") is None
        expect(page.locator(".markdown img")).to_have_count(0)
        assert page.locator('.markdown a[href^="javascript:"]').count() == 0
        page.get_by_test_id("knowledge-save").click()
        eventually(lambda: app.note(note_id)["body"] == body)
        eventually(lambda: app.note(note_id)["sync_status"] == "synced")
        indexed(app, note_id)
        expect(page.get_by_test_id("knowledge-body")).to_have_value(body)
        expect(page.get_by_test_id("markdown-preview")).to_contain_text("浏览器新增")
        for width in (1440, 1024, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            page.screenshot(path=str(evidence / f"note-editor-{width}.png"), full_page=True, animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Editor overflow at {width}"
        page.set_viewport_size({"width": 1440, "height": 1000})

        navigate(page, app, "/search")
        page.get_by_test_id("search-query").fill("数据库索引的成本是什么？")
        page.get_by_test_id("search-submit").click()
        expect(page.locator('#main a[href="#/knowledge/' + note_id + '"]')).to_be_visible(timeout=30000)
        page.get_by_role("tab", name="引用问答", exact=True).click()
        page.get_by_test_id("ask-question").fill("数据库索引的收益与成本是什么？")
        page.get_by_test_id("ask-submit").click()
        expect(page.get_by_test_id("ask-answer")).to_contain_text("引用与原文依据", timeout=30000)
        page.get_by_test_id("ask-answer").locator('a[href="#/knowledge/' + note_id + '"]').click()
        expect(page.get_by_test_id("knowledge-body")).to_have_value(body)

        body = check_lifecycle(page, app, note_id, body)
        navigate(page, app, "/processing/" + run["id"])
        page.get_by_test_id("processing-adopt").click()
        expect(page.get_by_test_id("knowledge-title")).to_be_visible()
        assert app.request("GET", "/api/v1/knowledge")["total"] == before_notes + 1
        check_disabled_and_failures(page, app, source_id)
        check_partial_import(page, app, input_path)

        state = {"source_id": source_id, "knowledge_id": note_id, "run_id": run["id"], "body": body,
                 "screens": [1440, 1024, 390], "workflow": "passed"}
        assert not errors, errors
        unexpected_console = [item for item in console if item["type"] == "error"
                              and not re.search(r"status of (409|429|503|504)", item["text"])]
        assert not unexpected_console, unexpected_console
        assert not external, f"Unexpected external browser requests: {external}"
        (evidence / "browser-workflow.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state
    except Exception:
        page.screenshot(path=str(evidence / "failure.png"), full_page=True, animations="disabled")
        (evidence / "failure.html").write_text(page.content(), encoding="utf-8")
        raise
    finally:
        (evidence / "browser-console.json").write_text(json.dumps({"page_errors": errors, "console": console,
            "external_requests": external}, ensure_ascii=False, indent=2), encoding="utf-8")
        context.tracing.stop(path=str(evidence / "browser-trace.zip"))
        context.close()
