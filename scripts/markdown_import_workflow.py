"""Real browser upload and sanitized report checks, shared by local and EXE."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from markdown_import_support import ENDPOINT, assert_public_report, check_report
from verification_support import PROJECT_VERSION, eventually


def check_disabled_and_counts(app, total: int):
    assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
    assert app.request("GET", "/api/v1/ai/profiles")["enabled"] is False
    assert app.request("GET", "/api/v1/rag/index/status")["enabled"] is False
    assert app.request("GET", "/api/v1/ui/sources?limit=1")["total"] == total
    assert app.request("GET", "/api/v1/ui/knowledge?limit=1")["total"] == 0
    assert app.request("GET", "/api/v1/processing/runs?limit=1")["total"] == 0


def import_in_browser(browser, page, app, corpus, evidence: Path, *, desktop: bool):
    page_errors, external, uploads = [], [], []
    page.on("pageerror", lambda error: page_errors.append(type(error).__name__))

    def observe(request):
        address = urlsplit(request.url)
        if address.hostname and address.hostname not in {"127.0.0.1", "localhost"}:
            external.append(address.hostname)
        if address.path == ENDPOINT and request.method == "POST":
            checked = corpus.check_upload(request.post_data_json)
            uploads.append({**checked, "dry_run": parse_qs(address.query)["dry_run"] == ["true"]})

    page.on("request", observe)
    page.goto(app.url + "/#/imports")
    page.get_by_role("tab", name="知乎 Markdown 文件夹", exact=True).click()
    page.get_by_test_id("import-directory").set_input_files(corpus.root, timeout=120000)
    expect(page.get_by_test_id("import-preview")).to_be_enabled(timeout=120000)
    expect(page.get_by_test_id("import-submit")).to_be_disabled()
    check_disabled_and_counts(app, 0)
    records = {}

    for stage, button, dry_run in (("preview", "import-preview", True), ("created", "import-submit", False),
                                   ("repeat_preview", "import-preview", True), ("repeated", "import-submit", False)):
        with page.expect_response(lambda response: urlsplit(response.url).path == ENDPOINT,
                                  timeout=180000) as pending:
            page.get_by_test_id(button).click()
        response = pending.value
        assert response.status == 200, "Markdown import API did not return HTTP 200"
        record = response.json()
        assert record["dry_run"] is dry_run
        check_report(record, corpus, stage=stage)
        records[stage] = record
        (evidence / f"{stage}-report.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        expect(page.get_by_test_id("import-preview")).to_be_enabled(timeout=120000)
        expect(page.get_by_test_id("import-report")).to_contain_text("报告共 571 条")
        check_disabled_and_counts(app, 0 if stage == "preview" else 571)
    assert len(uploads) == 4 and [item["dry_run"] for item in uploads] == [True, False, True, False]
    assert {item["source_id"] for item in records["created"]["items"]} == {
        item["source_id"] for item in records["repeated"]["items"]}

    # Export the actual on-screen report; neither report path contains source bodies.
    download_file = evidence / "downloaded-report.json"
    if desktop:
        exports = app.root / "exports"
        exports.mkdir(exist_ok=True)
        session = browser.new_browser_cdp_session()
        session.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(exports), "eventsEnabled": True})
        page.get_by_role("button", name="下载报告", exact=True).click()
        download_file = eventually(lambda: next((file for file in exports.glob("*.json") if file.is_file()), None))
    else:
        with page.expect_download(timeout=30000) as pending:
            page.get_by_role("button", name="下载报告", exact=True).click()
        pending.value.save_as(download_file)
    downloaded = json.loads(download_file.read_text(encoding="utf-8-sig"))
    assert_public_report(downloaded)
    check_report(downloaded, corpus, stage="repeated")
    page.get_by_role("button", name="报告下一页", exact=True).click()
    expect(page.get_by_test_id("import-report")).to_contain_text("第 2 页")
    page.screenshot(path=str(evidence / "markdown-import-report.png"), full_page=True)
    assert not page_errors, "Browser page errors occurred"
    assert not external, "A real export page attempted an external browser request"
    return records["created"], {"uploads": uploads, "report_download": True, "report_pagination": True,
        "reports_without_bodies": True, "page_errors": [], "external_browser_requests": 0,
        "preview_would_create": 571, "created": 571, "repeat_created": 0, "repeat_skipped": 571}
