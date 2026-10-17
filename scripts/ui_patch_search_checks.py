"""Measure both search tabs without starting a model or changing data."""

from playwright.sync_api import expect


def check_search_controls(page, api, evidence):
    cases = []
    expect(page.get_by_test_id("retrieval-limit")).to_have_value("5")
    for width in (1440, 1024, 390, 320):
        page.set_viewport_size({"width": width, "height": 1000})
        for tab in ("语义检索", "引用问答"):
            page.get_by_role("tab", name=tab, exact=True).click()
            geometry = page.evaluate("""() => {
                const box = node => {const r = node.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,center:r.y+r.height/2};};
                const field = document.querySelector('.search-limit-field');
                return {label:box(field.querySelector('label')), select:box(field.querySelector('select')),
                    tabs:box(document.querySelector('.search-toolbar .tabs')), field:box(field),
                    viewport:innerWidth, documentWidth:document.documentElement.scrollWidth};
            }""")
            assert abs(geometry["label"]["center"] - geometry["select"]["center"]) <= 1, geometry
            assert geometry["documentWidth"] <= width + 1, geometry
            if width >= 390:
                assert abs(geometry["tabs"]["center"] - geometry["field"]["center"]) <= 1, geometry
            assert geometry["select"]["width"] >= 100, geometry
            cases.append({"width": width, "tab": tab, "geometry": geometry})
            name = "ask" if tab == "引用问答" else "search"
            page.screenshot(path=str(evidence / f"{width}-{name}.png"), full_page=True, animations="disabled")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_label("检索数量", exact=True).select_option("7")
    page.get_by_role("tab", name="语义检索", exact=True).click()
    page.get_by_test_id("search-query").fill("布局不会改变检索参数")
    page.get_by_test_id("search-submit").click()
    expect(page.get_by_text("没有可用片段", exact=True)).to_be_visible()
    assert api.calls[-1]["body"]["top_k"] == 7
    page.get_by_role("tab", name="引用问答", exact=True).click()
    expect(page.get_by_label("检索数量", exact=True)).to_have_value("7")
    page.get_by_test_id("ask-question").fill("检索数量是否保留？")
    page.get_by_test_id("ask-submit").click()
    expect(page.get_by_test_id("ask-answer")).to_be_visible()
    assert api.calls[-1]["body"]["top_k"] == 7
    return {"status": "passed", "layouts": cases, "top_k_preserved": 7}
