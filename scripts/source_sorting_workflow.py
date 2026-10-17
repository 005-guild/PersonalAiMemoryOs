"""Real dropdown/header sorting, stable pages and read-only return context."""

from urllib.parse import parse_qs, urlencode

from playwright.sync_api import expect

from source_sorting_fixture import FIELDS, PREFIX, expected_groups

LABELS = {"title": "标题", "source_count": "资料数量", "source_type": "类型", "updated_at": "更新时间"}


def assert_sorted_page(page, records, field, order, *, number=1, state="active"):
    expected = expected_groups(records, field, order, state=state)
    titles = [item["title"] for item in expected[(number - 1) * 20:number * 20]]
    expect(page.get_by_test_id("source-group-link")).to_have_text(titles)
    expect(page.get_by_label("排序依据", exact=True)).to_have_value(field)
    expect(page.get_by_label("排序方向", exact=True)).to_have_value(order)
    active = page.locator("th").filter(has=page.get_by_role("button", name=f"按{LABELS[field]}排序", exact=True))
    expect(active).to_have_attribute("aria-sort", "ascending" if order == "asc" else "descending")
    expect(page.locator('th[aria-sort="ascending"],th[aria-sort="descending"]')).to_have_count(1)
    params = parse_qs(page.evaluate("location.hash").partition("?")[2])
    assert params.get("sort_by", ["updated_at"])[0] == field
    assert params.get("order", ["desc"])[0] == order
    assert int(params.get("page", ["1"])[0]) == number


def sorting_in_browser(page, app, records, evidence):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(app.url + "/#/sources?" + urlencode({"q": PREFIX, "state": "active", "page": 1, "per_page": 20}))
    assert_sorted_page(page, records, "updated_at", "desc")
    dropdowns = []
    for field in FIELDS:
        page.get_by_label("排序依据", exact=True).select_option(field)
        default = "asc" if field in {"title", "source_type"} else "desc"
        assert_sorted_page(page, records, field, default)
        for order in ("asc", "desc"):
            page.get_by_label("排序方向", exact=True).select_option(order)
            assert_sorted_page(page, records, field, order)
            page.get_by_role("navigation", name="资料标题分页", exact=True).get_by_role("button", name="第 2 页", exact=True).click()
            assert_sorted_page(page, records, field, order, number=2)
            dropdowns.append({"sort_by": field, "order": order, "page_2_verified": True})
    # Both public interaction surfaces must agree, including reverse on active header.
    headers = []
    for field in FIELDS:
        default = "asc" if field in {"title", "source_type"} else "desc"
        page.get_by_role("button", name=f"按{LABELS[field]}排序", exact=True).click()
        assert_sorted_page(page, records, field, default)
        page.get_by_role("button", name=f"按{LABELS[field]}排序", exact=True).click()
        assert_sorted_page(page, records, field, "desc" if default == "asc" else "asc")
        headers.append(field)
    page.get_by_label("记录状态", exact=True).select_option("all")
    page.get_by_label("排序依据", exact=True).select_option("source_type")
    assert_sorted_page(page, records, "source_type", "asc", state="all")
    page.screenshot(path=str(evidence / "sort-visible-minimum-type.png"), full_page=True)
    page.get_by_label("记录状态", exact=True).select_option("active")
    assert_sorted_page(page, records, "source_type", "asc")
    page.get_by_label("排序依据", exact=True).select_option("source_count")
    assert_sorted_page(page, records, "source_count", "desc")
    page.get_by_role("navigation", name="资料标题分页", exact=True).get_by_role("button", name="第 2 页", exact=True).click()
    assert_sorted_page(page, records, "source_count", "desc", number=2)
    list_hash = page.evaluate("location.hash")
    selected = expected_groups(records, "source_count", "desc")[20]
    page.get_by_test_id("source-group-link").first.click()
    expect(page.get_by_test_id("source-group-card")).to_have_count(selected["source_count"])
    group_hash = page.evaluate("location.hash")
    assert parse_qs(group_hash.partition("?")[2])["return_to"] == [list_hash]
    page.get_by_test_id("source-group-edit").first.click()
    expect(page.get_by_test_id("source-title")).to_have_value(selected["title"])
    assert parse_qs(page.evaluate("location.hash").partition("?")[2])["return_to"] == [group_hash]
    page.get_by_test_id("editor-back").click()
    expect(page.get_by_test_id("source-group-card")).to_have_count(selected["source_count"])
    assert page.evaluate("location.hash") == group_hash
    page.get_by_test_id("source-list-back").click()
    assert_sorted_page(page, records, "source_count", "desc", number=2)
    assert page.evaluate("location.hash") == list_hash
    page.screenshot(path=str(evidence / "sort-return-context.png"), full_page=True)
    assert not errors
    return {"dropdowns": dropdowns, "headers": headers, "visible_minimum_type": True,
            "pagination_and_return_context": True, "final_hash": list_hash, "page_errors": []}
