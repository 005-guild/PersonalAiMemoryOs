"""Browser scenarios for safe current-page selection and partial deletion."""

from urllib.parse import parse_qs

from playwright.sync_api import expect


def selected(page, count):
    expect(page.get_by_text(f"已选择 {count} 篇", exact=True)).to_be_visible()


def confirm(page, choice="移入回收站"):
    dialog = page.get_by_role("dialog", name="批量删除笔记", exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name=choice, exact=True).click()


def check_selection_and_cancel(page, api, evidence):
    boxes = page.get_by_test_id("knowledge-select")
    expect(boxes).to_have_count(4)
    boxes.first.focus()
    page.keyboard.press("Space")
    expect(boxes.first).to_be_checked()
    selected(page, 1)
    assert page.get_by_test_id("knowledge-select-all").evaluate("node => node.indeterminate")
    page.get_by_test_id("knowledge-select-all").check()
    selected(page, 4)
    page.get_by_test_id("knowledge-select-all").uncheck()
    selected(page, 0)
    boxes.first.check()
    boxes.nth(1).check()
    page.get_by_role("button", name="取消选择", exact=True).click()
    selected(page, 0)
    boxes.first.check()
    page.get_by_test_id("knowledge-bulk-delete").click()
    expect(boxes.first).to_be_disabled()
    expect(page.get_by_label("标题筛选", exact=True)).to_be_disabled()
    confirm(page, "取消")
    selected(page, 1)
    assert not api.deletions
    page.get_by_label("记录状态", exact=True).select_option("all")
    expect(boxes).to_have_count(5)
    selected(page, 0)
    deleted = page.get_by_label("选择笔记：笔记 02", exact=True)
    expect(deleted).to_be_disabled()
    page.get_by_test_id("knowledge-select-all").check()
    selected(page, 4)
    expect(deleted).not_to_be_checked()
    page.get_by_label("记录状态", exact=True).select_option("deleted")
    expect(boxes).to_have_count(1)
    selected(page, 0)
    expect(page.get_by_test_id("knowledge-select-all")).to_be_disabled()
    page.set_viewport_size({"width": 390, "height": 1000})
    page.screenshot(path=str(evidence / "knowledge-trash-390.png"), full_page=True, animations="disabled")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    return {"status": "passed", "delete_calls_after_cancel": len(api.deletions),
            "checks": ["single_keyboard", "indeterminate", "select_page", "deselect_all", "clear",
                       "cancel_no_writes", "all_state_excludes_deleted", "trash_disabled", "390_no_overflow"]}


def check_filter_and_loading(page, api, evidence):
    boxes = page.get_by_test_id("knowledge-select")
    expect(boxes).to_have_count(20)
    page.get_by_test_id("knowledge-select-all").check()
    selected(page, 20)
    assert len(api.notes) == 25
    page.get_by_test_id("knowledge-select-all").uncheck()
    boxes.first.check()
    # Clear immediately, rather than leaving a stale selection during debounce.
    with page.expect_response(lambda response: "/api/v1/ui/knowledge?" in response.url):
        page.get_by_label("标题筛选", exact=True).fill("笔记")
        selected(page, 0)
        expect(boxes.first).to_be_disabled()
        expect(page.get_by_test_id("knowledge-select-all")).to_be_disabled()
    expect(boxes.first).to_be_enabled()
    boxes.first.check()
    api.hold_lists = True
    page.get_by_role("button", name="下一页", exact=True).click()
    expect(page.get_by_test_id("knowledge-select-all")).to_be_disabled()
    expect(boxes.first).to_be_disabled()
    selected(page, 0)
    # Disabled stale DOM controls must also ignore programmatically dispatched events.
    page.get_by_test_id("knowledge-select-all").dispatch_event("change")
    page.wait_for_timeout(50)
    assert len(api.pending) == 1
    api.hold_lists = False
    api.finish_list()
    expect(page.get_by_role("link", name="笔记 21", exact=True)).to_be_visible()
    expect(boxes).to_have_count(5)
    selected(page, 0)
    boxes.first.check()
    page.get_by_role("button", name="上一页", exact=True).click()
    expect(page.get_by_role("link", name="笔记 01", exact=True)).to_be_visible()
    selected(page, 0)
    boxes.first.check()
    page.get_by_label("来源筛选", exact=True).fill("10000000-0000-4000-8000-000000000001")
    page.get_by_label("来源筛选", exact=True).press("Tab")
    selected(page, 0)
    page.set_viewport_size({"width": 390, "height": 1000})
    page.screenshot(path=str(evidence / "knowledge-selection-390.png"), full_page=True, animations="disabled")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    return {"status": "passed", "checks": ["current_page_only_20_of_25", "search_clear_before_debounce", "slow_get_disables_old_header",
            "stale_header_ignored", "next_previous_clear", "source_filter_clear", "390_no_overflow"]}


def check_stale_partial_delete(page, api, evidence):
    original = [dict(note) for note in api.notes.values()]
    page.get_by_test_id("knowledge-select-all").check()
    selected(page, 3)
    newer = api.notes[original[1]["id"]]
    newer.update(version=99, body="服务器已有新内容，不得删除或覆盖。")
    page.get_by_test_id("knowledge-bulk-delete").click()
    confirm(page)
    report = page.get_by_test_id("knowledge-bulk-report")
    expect(report).to_contain_text("已移入回收站 2 篇，未完成 1 篇")
    expect(report).to_contain_text("笔记已变化，未删除")
    expect(page.get_by_role("link", name=original[1]["title"], exact=True).last).to_be_visible()
    assert len(api.deletions) == 3
    assert [call["path"].rsplit("/", 1)[-1] for call in api.deletions] == [note["id"] for note in original]
    assert [int(parse_qs(call["query"])["expected_version"][0]) for call in api.deletions] == [note["version"] for note in original]
    assert newer["version"] == 99 and newer["deleted_at"] is None
    assert newer["body"] == "服务器已有新内容，不得删除或覆盖。"
    selected(page, 0)
    page.screenshot(path=str(evidence / "bulk-stale-report.png"), full_page=True, animations="disabled")
    return {"status": "passed", "delete_calls": api.deletions, "new_content_retained": True,
            "other_deletes_succeeded": 2, "automatic_retries": 0}


def check_network_stop(page, api, evidence):
    ids = list(api.notes)
    api.failures[ids[1]] = "abort_after_commit"
    page.get_by_test_id("knowledge-select-all").check()
    page.get_by_test_id("knowledge-bulk-delete").click()
    confirm(page)
    report = page.get_by_test_id("knowledge-bulk-report")
    expect(report).to_contain_text("已移入回收站 1 篇，未完成 2 篇")
    expect(report).to_contain_text("无法确认删除结果")
    expect(report).to_contain_text("尚未提交删除")
    assert [call["path"].rsplit("/", 1)[-1] for call in api.deletions] == ids[:2]
    assert api.notes[ids[1]]["deleted_at"] and not api.notes[ids[2]]["deleted_at"]
    page.screenshot(path=str(evidence / "bulk-network-report.png"), full_page=True, animations="disabled")
    return {"status": "passed", "delete_calls": api.deletions, "unknown_committed_result_not_retried": True,
            "remaining_item_not_submitted": ids[2], "automatic_retries": 0}


def check_last_page(page, api, evidence):
    page.get_by_role("button", name="下一页", exact=True).click()
    expect(page.get_by_test_id("knowledge-select")).to_have_count(1)
    page.get_by_test_id("knowledge-select-all").check()
    selected(page, 1)
    page.get_by_test_id("knowledge-bulk-delete").click()
    confirm(page)
    expect(page.get_by_test_id("knowledge-select")).to_have_count(20)
    expect(page.get_by_text("共 20 条 · 第 1 页", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="上一页", exact=True)).to_be_disabled()
    assert len(api.deletions) == 1
    selected(page, 0)
    page.screenshot(path=str(evidence / "bulk-last-page-fallback.png"), full_page=True, animations="disabled")
    return {"status": "passed", "delete_calls": api.deletions, "returned_to_page": 1}
