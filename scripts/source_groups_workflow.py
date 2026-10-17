"""Synthetic source-group pagination checks against a real running workbench."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlencode, urlsplit

from playwright.sync_api import expect

from verification_support import PROJECT_VERSION

SHARED_TITLE = "分组分页验收标题"
GROUPS = "/api/v1/ui/source-groups"


def seed_sources(app):
    records, shared = {}, []
    # Create this group first so it is initially on page 3 (46 groups at size 20).
    for index, author in enumerate(("作者甲", "作者乙", "作者丙")):
        content = (f"# {author}的独立原文\n同标题资料编号 {index + 1}，不能与其他来源合并。\n"
                   + f"{author}的完整资料段落，保留原文及上下文。\n" * 20
                   + f"仅存在于完整正文末尾的{author}标记。")
        record = app.request("POST", "/api/v1/sources", {"source_type": "manual", "title": SHARED_TITLE,
            "author": author, "content": content})
        records[record["id"]] = record
        shared.append(record["id"])
    for index in range(45):
        record = app.request("POST", "/api/v1/sources", {"source_type": "manual", "title": f"{SHARED_TITLE} {index:02d}",
            "author": f"独立作者{index:02d}", "content": f"第 {index + 1} 个唯一标题的独立正文。"})
        records[record["id"]] = record
    groups = app.request("GET", GROUPS + "?limit=100")
    assert groups["total"] == 46 and groups["total_sources"] == 48
    assert len({item["title"] for item in groups["items"]}) == 46
    members = app.request("GET", GROUPS + "/items?" + urlencode({"title": SHARED_TITLE}))
    assert members["total"] == 3 and {item["id"] for item in members["items"]} == set(shared)
    return records, shared


def list_context(page, *, number, per_page):
    params = parse_qs(page.evaluate("location.hash").partition("?")[2])
    assert params.get("q", [""])[0] == SHARED_TITLE
    assert params.get("state", ["active"])[0] == "active"
    assert int(params.get("page", ["1"])[0]) == number
    assert int(params.get("per_page", ["20"])[0]) == per_page


def verify_source_groups(browser, page, app, evidence: Path, records: dict, shared: list[str]):
    page_errors, external = [], []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost", None} else None)
    assert app.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
    route = "#/sources?" + urlencode({"q": SHARED_TITLE, "state": "active", "page": 1, "per_page": 20})
    page.goto(app.url + "/" + route)
    links = page.get_by_test_id("source-group-link")
    expect(links).to_have_count(20)
    pager = page.get_by_role("navigation", name="资料标题分页", exact=True)
    expect(pager).to_be_visible()
    expect(page.get_by_label("每页标题数", exact=True)).to_have_value("20")
    expected = app.request("GET", GROUPS + "?" + urlencode({"q": SHARED_TITLE, "offset": 0, "limit": 20}))
    assert links.all_text_contents() == [item["title"] for item in expected["items"]]
    page.screenshot(path=str(evidence / "source-groups-page-1.png"), full_page=True)

    pager.get_by_role("button", name="第 2 页", exact=True).click()
    expect(links).to_have_count(20)
    expect(page).to_have_url(re.compile(r"page=2(?:&|$)"))
    second_page = app.request("GET", GROUPS + "?" + urlencode({"q": SHARED_TITLE, "offset": 20, "limit": 20}))
    expect(links).to_have_text([item["title"] for item in second_page["items"]])
    list_context(page, number=2, per_page=20)
    pager = page.get_by_role("navigation", name="资料标题分页", exact=True)
    pager.get_by_label("跳转页码", exact=True).fill("3")
    pager.get_by_role("button", name="跳转", exact=True).click()
    expect(links).to_have_count(6)
    list_context(page, number=3, per_page=20)

    page.get_by_label("每页标题数", exact=True).select_option("50")
    expect(links).to_have_count(46)
    list_context(page, number=1, per_page=50)
    page.screenshot(path=str(evidence / "source-groups-page-size-50.png"), full_page=True)
    page.get_by_label("每页标题数", exact=True).select_option("20")
    expect(links).to_have_count(20)
    pager = page.get_by_role("navigation", name="资料标题分页", exact=True)
    pager.get_by_label("跳转页码", exact=True).fill("3")
    pager.get_by_role("button", name="跳转", exact=True).click()
    expect(links).to_have_count(6)
    list_context(page, number=3, per_page=20)
    page.get_by_role("link", name=SHARED_TITLE, exact=True).click()
    cards = page.get_by_test_id("source-group-card")
    expect(cards).to_have_count(3)
    group_hash = page.evaluate("location.hash")
    assert group_hash.startswith("#/sources/group?")
    params = parse_qs(group_hash.partition("?")[2])
    assert params["title"] == [SHARED_TITLE]
    assert {card.get_attribute("data-source-id") for card in cards.all()} == set(shared)
    for source_id in shared:
        card = page.locator(f'[data-testid="source-group-card"][data-source-id="{source_id}"]')
        expect(card).to_contain_text(records[source_id]["author"])
        expect(card).to_contain_text(records[source_id]["content"].splitlines()[1])
        expect(card).to_contain_text(records[source_id]["content"].splitlines()[-1])
    page.screenshot(path=str(evidence / "three-independent-source-bodies.png"), full_page=True)

    changed_id = shared[0]
    card = page.locator(f'[data-testid="source-group-card"][data-source-id="{changed_id}"]')
    card.get_by_test_id("source-group-edit").click()
    expect(page.get_by_test_id("source-content")).to_have_value(records[changed_id]["content"])
    editor_params = parse_qs(page.evaluate("location.hash").partition("?")[2])
    assert editor_params["return_to"] == [group_hash]
    new_content = records[changed_id]["content"] + "\n通过分组入口追加编辑，仍保持独立来源。"
    page.get_by_test_id("source-content").fill(new_content)
    with page.expect_response(lambda response: response.request.method == "PATCH"
            and urlsplit(response.url).path == f"/api/v1/sources/{changed_id}") as pending:
        page.get_by_test_id("source-save").click()
    assert pending.value.status == 200
    records[changed_id] = pending.value.json()
    expect(page.get_by_test_id("source-save")).to_be_enabled()
    page.get_by_test_id("editor-back").click()
    expect(page.get_by_test_id("source-group-card")).to_have_count(3)
    assert page.evaluate("location.hash") == group_hash
    expect(page.locator(f'[data-testid="source-group-card"][data-source-id="{changed_id}"]')).to_contain_text("通过分组入口追加编辑")
    page.get_by_test_id("source-list-back").click()
    expect(page.get_by_test_id("source-group-link")).to_have_count(6)
    list_context(page, number=3, per_page=20)
    page.screenshot(path=str(evidence / "returned-list-context.png"), full_page=True)
    assert not page_errors and not external
    return {"groups": 46, "sources": 48, "same_title_members": 3, "page_size_20": True,
            "page_size_50": True, "numeric_page": True, "input_jump": True, "exact_group": True,
            "independent_bodies": True, "edit_group_list_context": True, "page_errors": [],
            "external_browser_requests": 0, "changed_source_id": changed_id}


def assert_source_storage(database: Path, records: dict):
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = {row["id"]: row for row in connection.execute("SELECT * FROM sources")}
        assert len(rows) == len(records) == 48
        assert len({row["title"] for row in rows.values()}) == 46
        for source_id, expected in records.items():
            row = rows[source_id]
            assert row["title"] == expected["title"] and row["author"] == expected["author"]
            assert row["version"] == expected["version"] and row["deleted_at"] is None
            assert hashlib.sha256(row["content"].encode()).digest() == hashlib.sha256(expected["content"].encode()).digest()
        for table in ("source_origins", "knowledge", "processing_runs", "rag_index_generations", "rag_note_index_states", "rag_index_jobs"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    return {"sources": 48, "groups": 46, "no_physical_merge": True, "all_source_hashes_verified": True,
            "knowledge": 0, "processing_runs": 0, "sqlite_integrity": "ok"}
