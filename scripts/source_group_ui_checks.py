"""Group paging, safe reading and local return routes in real Chromium."""

import re
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect
from source_group_ui_fixtures import SHARED


def pager(page):return page.get_by_role('navigation',name='资料标题分页',exact=True)


def check_group_paging(page,api,evidence):
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    expect(page.get_by_test_id('source-group-count')).to_contain_text('46 个标题')
    pager(page).get_by_role('button',name='第 3 页',exact=True).click()
    expect(page.get_by_test_id('source-group-link')).to_have_count(6)
    assert parse_qs(urlsplit(page.url.split('#',1)[1]).query)['page']==['3']
    pager(page).get_by_label('每页标题数',exact=True).select_option('50')
    expect(page.get_by_test_id('source-group-link')).to_have_count(46)
    assert parse_qs(urlsplit(page.url.split('#',1)[1]).query)['page']==['1']
    pager(page).get_by_label('每页标题数',exact=True).select_option('20')
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    pager(page).get_by_label('跳转页码',exact=True).fill('0')
    pager(page).get_by_role('button',name='跳转',exact=True).click()
    expect(page.get_by_text('请输入 1 至 3 之间的整数页码。',exact=True)).to_be_visible()
    pager(page).get_by_label('跳转页码',exact=True).fill('3')
    pager(page).get_by_label('跳转页码',exact=True).press('Enter')
    expect(page.get_by_test_id('source-group-link')).to_have_count(6)
    original_hash=page.evaluate('location.hash')
    page.reload()
    expect(page.get_by_test_id('source-group-link')).to_have_count(6)
    page.get_by_test_id('source-group-link').first.click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(1)
    group_hash=page.evaluate('location.hash')
    page.get_by_test_id('source-group-edit').click()
    expect(page.get_by_test_id('source-author')).to_be_visible()
    page.get_by_test_id('source-author').fill('编辑后作者')
    page.get_by_test_id('source-save').click()
    expect(page.get_by_test_id('source-author')).to_have_value('编辑后作者')
    assert parse_qs(urlsplit(page.url.split('#',1)[1]).query)['return_to']==[group_hash]
    page.get_by_test_id('editor-back').click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(1)
    assert page.evaluate('location.hash')==group_hash
    page.get_by_test_id('source-list-back').click()
    expect(page.get_by_test_id('source-group-link')).to_have_count(6)
    assert page.evaluate('location.hash')==original_hash
    pager(page).get_by_role('button',name='首页',exact=True).click()
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    page.get_by_label('标题筛选',exact=True).focus()
    page.keyboard.type('标题')
    expect(page.get_by_label('标题筛选',exact=True)).to_be_focused()
    page.wait_for_timeout(400)
    expect(page.get_by_label('标题筛选',exact=True)).to_be_focused()
    page.keyboard.type(' 01')
    page.wait_for_timeout(400)
    expect(page.get_by_label('标题筛选',exact=True)).to_have_value('标题 01')
    expect(page.get_by_label('标题筛选',exact=True)).to_be_focused()
    expect(page.get_by_test_id('source-group-link')).to_have_count(1)
    page.get_by_label('标题筛选',exact=True).fill('')
    page.wait_for_timeout(400)
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    expect(page.get_by_label('标题筛选',exact=True)).to_be_focused()
    page.get_by_label('记录状态',exact=True).select_option('all')
    expect(page.get_by_test_id('source-group-count')).to_contain_text('52 篇资料')
    page.set_viewport_size({'width':390,'height':1000})
    page.screenshot(path=str(evidence/'source-pages-390.png'),full_page=True,animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    return {'status':'passed','title_groups':46,'page_sizes':[20,50],'jump_validation':True,'refresh_and_return_context':True,'slow_filter_focus_retained':True,'mobile_no_overflow':True}


def check_group_reading(page,api,evidence):
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    page.get_by_role('link',name=SHARED,exact=True).click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(5)
    expect(page.get_by_test_id('source-member-count')).to_contain_text('共 6 篇')
    first=page.get_by_test_id('source-group-card').first
    expect(first).to_contain_text('答案 0 的完整尾标记')
    assert page.evaluate('window.__unsafeSource') is None
    assert page.locator('.source-reading img,.source-reading script,.source-reading a[href^="javascript:"]').count()==0
    page.get_by_role('button',name='完整纯文本阅读',exact=True).click()
    text=page.get_by_test_id('source-full-text').input_value()
    assert len(text)>100000 and text.endswith('末尾不截断')
    expect(page.get_by_test_id('source-full-text')).to_have_attribute('readonly','')
    first.locator('summary').first.click()
    assert not first.locator('details.source-reading').evaluate('node=>node.open')
    first.locator('summary').first.click()
    navigation=page.get_by_role('navigation',name='同标题资料分页',exact=True)
    navigation.get_by_role('button',name='下一页',exact=True).click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(1)
    navigation.get_by_label('每页资料数',exact=True).select_option('10')
    expect(page.get_by_test_id('source-group-card')).to_have_count(6)
    page.get_by_label('组内记录状态',exact=True).select_option('all')
    expect(page.get_by_test_id('source-group-card')).to_have_count(7)
    expect(page.get_by_text('已删除',exact=True)).to_be_visible()
    page.set_viewport_size({'width':390,'height':1000})
    page.screenshot(path=str(evidence/'source-reader-390.png'),full_page=False,animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    return {'status':'passed','default_members_per_page':5,'member_page_sizes':[5,10], 'exact_title_group':True,
            'full_original_bodies':True,'safe_markdown':True,'long_body_characters':len(text),'read_only_full_text':True,'deleted_visible_in_all':True,'mobile_no_overflow':True}


def check_body_concurrency_and_dispose(page,api,evidence):
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    api.hold_bodies=True
    page.get_by_role('link',name=SHARED,exact=True).click()
    page.wait_for_timeout(100)
    assert len(api.pending)==3 and api.maximum_bodies==3
    api.finish_body()
    page.wait_for_timeout(100)
    assert len(api.pending)==3 and api.maximum_bodies==3
    page.locator('#navigation a[href="#/knowledge"]').click()
    expect(page.get_by_role('heading',name='知识笔记',exact=True)).to_be_visible()
    while api.pending:api.finish_body()
    page.wait_for_timeout(100)
    assert page.get_by_test_id('source-group-card').count()==0
    assert page.get_by_role('heading',name='知识笔记',exact=True).count()==1
    return {'status':'passed','maximum_body_concurrency':api.maximum_bodies,'late_disposed_body_ignored':True,'knowledge_route_unchanged':True}


def check_conflict_restore_context(page,api,evidence):
    expect(page.get_by_test_id('source-group-link')).to_have_count(20)
    page.get_by_role('link',name=SHARED,exact=True).click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(5)
    group_hash=page.evaluate('location.hash')
    page.get_by_test_id('source-group-edit').first.click()
    expect(page.get_by_test_id('source-author')).to_be_visible()
    source_id=page.url.split('#/sources/',1)[1].split('?',1)[0]
    api.records[source_id].update(version=2,author='服务器并发作者')
    page.get_by_test_id('source-author').fill('本地保留作者')
    page.get_by_test_id('source-save').click()
    expect(page.get_by_text('比较本地输入与服务器版本',exact=True)).to_be_visible()
    expect(page.get_by_test_id('source-author')).to_have_value('本地保留作者')
    page.get_by_role('button',name='载入服务器版本',exact=True).click()
    page.get_by_role('dialog').get_by_role('button',name='确认',exact=True).click()
    expect(page.get_by_test_id('source-author')).to_have_value('服务器并发作者')
    assert parse_qs(urlsplit(page.url.split('#',1)[1]).query)['return_to']==[group_hash]
    page.get_by_test_id('editor-back').click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(5)
    page.get_by_role('navigation',name='同标题资料分页',exact=True).get_by_label('每页资料数',exact=True).select_option('10')
    expect(page.get_by_test_id('source-group-card')).to_have_count(6)
    page.get_by_label('组内记录状态',exact=True).select_option('all')
    expect(page.get_by_test_id('source-group-card')).to_have_count(7)
    restored_group_hash=page.evaluate('location.hash')
    page.get_by_role('link',name='查看与恢复资料',exact=True).click()
    page.get_by_test_id('entity-restore').click()
    expect(page.get_by_test_id('source-save')).to_be_enabled()
    assert parse_qs(urlsplit(page.url.split('#',1)[1]).query)['return_to']==[restored_group_hash]
    page.get_by_test_id('editor-back').click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(7)
    assert page.evaluate('location.hash')==restored_group_hash
    return {'status':'passed','stale_input_preserved':True,'reload_return_context':True,'restore_return_context':True}
