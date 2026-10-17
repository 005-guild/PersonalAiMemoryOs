"""Real Chromium checks of eight global Source sorts and retained navigation."""

import re
from urllib.parse import parse_qs

from playwright.sync_api import expect


def check_source_sorting(page, api, evidence):
    links = page.get_by_test_id('source-group-link')
    field = page.get_by_label('排序依据', exact=True)
    direction = page.get_by_label('排序方向', exact=True)
    pager = page.get_by_role('navigation', name='资料标题分页', exact=True)
    expect(field).to_have_value('updated_at')
    expect(direction).to_have_value('desc')
    expect(links).to_have_text(api.expected_titles('updated_at', 'desc')[:20])
    cases = []
    for sort_by in ['title', 'source_count', 'source_type', 'updated_at']:
        field.focus()
        field.select_option(sort_by)
        expect(direction).to_have_value('asc' if sort_by in ['title', 'source_type'] else 'desc')
        expect(field).to_be_focused()
        for order in ['asc', 'desc']:
            direction.focus()
            direction.select_option(order)
            expected = api.expected_titles(sort_by, order)
            expect(links).to_have_text(expected[:20])
            expect(direction).to_be_focused()
            params = parse_qs(page.evaluate('location.hash').partition('?')[2])
            assert params['sort_by'] == [sort_by] and params['order'] == [order] and params['page'] == ['1'], params
            rows = links.all_text_contents()
            pager.get_by_role('button', name='第 2 页', exact=True).click()
            expect(links).to_have_text(expected[20:40]); rows += links.all_text_contents()
            pager.get_by_label('跳转页码', exact=True).fill('3')
            pager.get_by_label('跳转页码', exact=True).press('Enter')
            expect(links).to_have_text(expected[40:]); rows += links.all_text_contents()
            assert rows == expected and len(set(rows)) == 45, (sort_by, order, rows)
            calls = [call for call in api.calls if call['path'] == '/api/v1/ui/source-groups']
            latest = parse_qs(calls[-1]['query'])
            assert latest['sort_by'] == [sort_by] and latest['order'] == [order] and latest['offset'] == ['40'], latest
            cases.append({'sort_by': sort_by, 'order': order, 'global_records_verified': 45})
    labels = {'title': '标题', 'source_count': '资料数量', 'source_type': '类型', 'updated_at': '更新时间'}
    for sort_by, label in labels.items():
        header = page.get_by_role('button', name=f'按{label}排序', exact=True)
        header.focus(); header.press('Enter')
        default = 'asc' if sort_by in ['title', 'source_type'] else 'desc'
        expect(field).to_have_value(sort_by); expect(direction).to_have_value(default)
        expect(links).to_have_text(api.expected_titles(sort_by, default)[:20])
        expect(header.locator('..')).to_have_attribute('aria-sort', 'ascending' if default == 'asc' else 'descending')
        header.click()
        reverse = 'desc' if default == 'asc' else 'asc'
        expect(direction).to_have_value(reverse)
        expect(header.locator('..')).to_have_attribute('aria-sort', 'ascending' if reverse == 'asc' else 'descending')
        expect(links).to_have_text(api.expected_titles(sort_by, reverse)[:20])
    group_calls = lambda: [call for call in api.calls if call['path'] == '/api/v1/ui/source-groups']
    previous_calls = len(group_calls())
    page.get_by_label('标题筛选', exact=True).fill('排序标题 0')
    field.focus(); field.select_option('title')
    expect(links).to_have_text(api.expected_titles('title', 'asc', query='排序标题 0'))
    page.wait_for_timeout(400)
    assert len(group_calls()) == previous_calls + 1, group_calls()[previous_calls:]
    expect(field).to_be_focused()
    base = page.url.split('#', 1)[0]
    page.goto(base + '#/sources?sort_by=source_type&order=desc&page=999&per_page=20')
    expect(links).to_have_text(api.expected_titles('source_type', 'desc')[40:])
    params = parse_qs(page.evaluate('location.hash').partition('?')[2])
    assert params['sort_by'] == ['source_type'] and params['order'] == ['desc'] and params['page'] == ['3'], params
    field.select_option('source_count')
    page.get_by_label('每页标题数', exact=True).select_option('50')
    expect(links).to_have_text(api.expected_titles('source_count', 'desc'))
    page.get_by_label('每页标题数', exact=True).select_option('20')
    expect(links).to_have_count(20)
    page.get_by_label('标题筛选', exact=True).fill('排序标题')
    expect(page).to_have_url(re.compile(r'q=%E6%8E%92%E5%BA%8F%E6%A0%87%E9%A2%98'))
    expect(page.get_by_label('标题筛选', exact=True)).to_be_focused()
    page.get_by_label('记录状态', exact=True).select_option('all')
    expect(links).to_have_text(api.expected_titles('source_count', 'desc', state='all')[:20])
    pager.get_by_role('button', name='第 2 页', exact=True).click()
    expected = api.expected_titles('source_count', 'desc', state='all')
    expect(links).to_have_text(expected[20:40])
    list_hash = page.evaluate('location.hash')
    page.reload(); expect(links).to_have_text(expected[20:40])
    page.get_by_role('button', name='＋ 新建资料', exact=True).click()
    assert parse_qs(page.evaluate('location.hash').partition('?')[2])['return_to'] == [list_hash]
    page.get_by_test_id('editor-back').click(); expect(links).to_have_text(expected[20:40])
    links.first.click()
    expect(page.get_by_test_id('source-group-card').first).to_be_visible()
    group_hash = page.evaluate('location.hash')
    assert parse_qs(group_hash.partition('?')[2])['return_to'] == [list_hash]
    page.get_by_test_id('source-group-edit').first.click()
    expect(page.get_by_test_id('source-author')).to_be_visible()
    page.get_by_test_id('source-author').fill('排序上下文验收作者')
    page.get_by_test_id('source-save').click()
    expect(page.get_by_test_id('source-author')).to_have_value('排序上下文验收作者')
    assert parse_qs(page.evaluate('location.hash').partition('?')[2])['return_to'] == [group_hash]
    page.get_by_test_id('editor-back').click()
    expect(page.get_by_test_id('source-group-card').first).to_be_visible()
    page.get_by_test_id('source-list-back').click()
    expect(links).to_have_text(expected[20:40])
    assert page.evaluate('location.hash') == list_hash
    page.screenshot(path=str(evidence / 'source-sort-1440.png'), full_page=True, animations='disabled')
    page.set_viewport_size({'width': 390, 'height': 1000})
    expect(field).to_be_visible(); expect(direction).to_be_visible()
    assert field.bounding_box()['width'] > 120 and direction.bounding_box()['width'] > 120
    field.select_option('updated_at'); direction.select_option('asc')
    expect(field).to_have_value('updated_at'); expect(direction).to_have_value('asc')
    page.screenshot(path=str(evidence / 'source-sort-390.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    return {'status': 'passed', 'sorts': cases, 'keyboard_headers': True, 'aria_sort': True,
            'sort_select_focus_retained': True, 'pending_filter_sort_single_request': True, 'clamp_preserves_sort': True,
            'per_page_filter_and_state_preserved': True, 'new_detail_edit_return_context': True, 'mobile_four_fields_available': True}
