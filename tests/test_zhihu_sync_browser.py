"""Real Chromium against synthetic pages; never contact Zhihu or use personal sessions."""

import json
from pathlib import Path

import pytest

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.browser import ZhihuBrowser
from app.services.zhihu_sync.storage import SyncError


@pytest.fixture
def browser(tmp_path):
    root = Path(__file__).resolve().parents[1]
    if not list((root/'.cache/playwright').glob('chromium-*/chrome-win64/chrome.exe')):
        pytest.skip('Matching Chromium is required for isolated browser acceptance')
    with ZhihuBrowser(tmp_path) as browser:
        browser.context.route('**/*',lambda route:route.fulfill(status=404,body='Unexpected request'))
        yield browser


def fixture(count=1, body='', paging=''):
    state=json.dumps({'initialState':{'entities':{'favlists':{'123':{'itemCount':count}}}}})
    return f'<html><head><script id="js-initialData" type="application/json">{state}</script></head><body><div class="CollectionsDetailPage-list">{body}</div>{paging}</body></html>'


def test_login_wall_is_not_an_empty_successful_collection(browser):
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(body='请登录后查看'),content_type='text/html; charset=utf-8'))
    with pytest.raises(SyncError,match='login_required'):
        browser.collection('https://www.zhihu.com/collection/123')


@pytest.mark.parametrize('row_class', ['List-item', 'CollectionDetailPageItem'])
def test_pagination_and_long_ids_are_not_rounded(browser, row_class):
    first=f'<div class="{row_class}"><a href="/question/1/answer/2000991203269820437">第一项</a></div>'
    next_body=f'<div class="{row_class}"><a href="https://zhuanlan.zhihu.com/p/1234">第二项</a></div>'
    script=json.dumps(next_body)
    paging=f'''<button onclick='document.querySelector(".CollectionsDetailPage-list").innerHTML={script};this.disabled=true'>下一页</button>'''
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(2,first,paging),content_type='text/html; charset=utf-8'))
    identities=browser.collection('https://www.zhihu.com/collection/123')
    assert [(x.resource_type,x.external_id) for x in identities] == [('answer','2000991203269820437'),('article','1234')]


def test_login_recognizes_current_collection_rows(browser):
    row='<div class="CollectionDetailPageItem"><a href="/question/1/answer/2">正文</a></div>'
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(1,row),content_type='text/html; charset=utf-8'))
    browser.login('https://www.zhihu.com/collection/123')


def test_collection_waits_for_placeholder_to_be_replaced(browser):
    placeholder='<div class="PlaceHolder CollectionDetailPageItem CollectionDetailPageItem--placeholder"></div>'
    row='<div class="CollectionDetailPageItem"><a href="/question/1/answer/2">正文</a></div>'
    script=f'<script>setTimeout(()=>document.querySelector(".CollectionsDetailPage-list").innerHTML={json.dumps(row)},600)</script>'
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(1,placeholder,script),content_type='text/html; charset=utf-8'))
    assert [x.external_id for x in browser.collection('https://www.zhihu.com/collection/123')] == ['2']


def test_missing_page_does_not_look_like_a_complete_scan(browser):
    row='<div class="List-item"><a href="/question/1/answer/2">条目</a></div>'
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(body=fixture(2,row),content_type='text/html; charset=utf-8'))
    with pytest.raises(SyncError,match='collection_changed_or_incomplete'):
        browser.collection('https://www.zhihu.com/collection/123')


def test_server_confirmed_gap_is_reported_without_becoming_complete(browser):
    endpoint='https://www.zhihu.com/api/v4/collections/123/items?offset=0&limit=20'
    payload={'paging':{'totals':2,'is_start':True,'is_end':True},
             'data':[{'content':{'type':'answer','id':'2'}}]}
    browser.context.route(endpoint,lambda route:route.fulfill(json=payload))
    row='<div class="CollectionDetailPageItem"><a href="/question/1/answer/2">正文</a></div>'
    script=f'<script>fetch({json.dumps(endpoint)}).then(r=>r.json()).then(()=>document.querySelector(".CollectionsDetailPage-list").innerHTML={json.dumps(row)})</script>'
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(2,'',script),content_type='text/html; charset=utf-8'))
    assert [x.external_id for x in browser.collection('https://www.zhihu.com/collection/123')] == ['2']
    assert browser.unlisted_count == 1


def test_collected_full_answer_needs_no_detail_request(browser):
    endpoint='https://www.zhihu.com/api/v4/collections/123/items?offset=0&limit=20'
    content={'type':'answer','id':'2','answer_type':'NORMAL','is_normal':True,
             'question':{'id':'1','title':'问题'},'content':'<p>完整正文</p>','excerpt':'摘要'}
    browser.context.route(endpoint,lambda route:route.fulfill(json={
        'paging':{'totals':1,'is_start':True,'is_end':True},'data':[{'content':content}]}))
    row='<div class="CollectionDetailPageItem"><a href="/question/1/answer/2">正文</a></div>'
    script=f'<script>fetch({json.dumps(endpoint)}).then(r=>r.json()).then(()=>document.querySelector(".CollectionsDetailPage-list").innerHTML={json.dumps(row)})</script>'
    browser.context.route('https://www.zhihu.com/collection/123',lambda route:route.fulfill(
        body=fixture(1,'',script),content_type='text/html; charset=utf-8'))
    identities=browser.collection('https://www.zhihu.com/collection/123')
    def unexpected_request(_):
        pytest.fail('A cached full answer must not navigate to the detail page')
    browser._goto=unexpected_request
    assert browser.article(identities[0])['html']=='<p>完整正文</p>'


def test_answer_keeps_only_body_and_not_comments(browser):
    identity=normalize_zhihu_url('https://www.zhihu.com/question/1/answer/2')
    html='''<h1 class="QuestionHeader-title">问题标题</h1><div class="AnswerItem">
      <span class="AuthorInfo-name">作者</span><div class="RichContent-inner"><div class="RichText"><p>完整正文</p></div></div>
      <div class="Comments-container">无关评论</div></div>'''
    browser.context.route(identity.canonical_url,lambda route:route.fulfill(body=html,content_type='text/html; charset=utf-8'))
    item=browser.article(identity)
    assert item['title']=='问题标题' and item['author']=='作者'
    assert '完整正文' in item['html'] and '无关评论' not in item['html']
