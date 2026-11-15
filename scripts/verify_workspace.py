"""Source/frozen navigation acceptance using isolated synthetic data; no paid calls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.desktop.server import DesktopServer
from app.repositories.database import Database
from app.services.content import ContentService
from desktop_verification_support import FrozenDesktop, attach_window
from reading_verification_support import seed
from verify_reading import snapshot
from v06_acceptance import browser_environment
from playwright.sync_api import sync_playwright, expect


def checks(page,url,note_id,folder):
    errors,mutations,external,requests=[],[],[],[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def request(r):
        requests.append(r.url)
        if r.method not in {'GET','HEAD'}:mutations.append(r.url)
        if not r.url.startswith((url,'data:','about:')):external.append(r.url)
    page.on('request',request)
    page.goto(url+'/#/')
    expect(page.locator('.reading-card')).to_have_count(6)
    expect(page.locator('#navigation .nav-link')).to_have_count(4)
    page.goto(url+'/#/reading/browse?scope=other')
    expect(page.locator('.reading-card')).to_have_count(1)
    page.locator('.reading-note-link').click()
    expect(page.get_by_role('heading',name='普通笔记验收',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='生成详细摘要候选')).to_have_count(0)
    page.get_by_role('link',name='编辑与整理',exact=True).click()
    expect(page.get_by_role('link',name='编辑正文与分类')).to_be_visible()
    expect(page.get_by_role('button',name='生成详细摘要候选')).to_have_count(0)
    page.goto(url+'/#/search?mode=keyword&q=独有检索词')
    expect(page.locator('.reading-card')).to_have_count(1)
    page.locator('.reading-note-link').click()
    page.get_by_role('link',name='← 返回阅读列表').click()
    expect(page.get_by_label('关键词',exact=True)).to_have_value('独有检索词')
    for route,heading in [('workbench','整理工作台'),('settings','设置'),('organization','收藏整理'),('organization/config','整理规则与预算'),
        ('organization/records','处理记录'),('organization/review','样本审核'),('organization/jobs','任务记录'),
        ('processing','AI 分析'),('processing/history','分析历史'),('drafts','草稿箱'),('sources','资料库'),('knowledge','知识笔记'),
        ('imports','资料导入'),('prompts','提示词中心'),('system','系统维护'),('system/sync','系统维护'),('system/index','系统维护'),
        ('system/conflicts','系统维护'),('settings/ai','AI 模型'),('settings/rag','向量检索'),('settings/zhihu','知乎同步'),('settings/storage','存储与关于')]:
        page.goto(url+'/#/'+route)
        expect(page.get_by_role('heading',name=heading,exact=True).first).to_be_visible()
        page.wait_for_load_state('networkidle')
        if route=='settings':
            expect(page.locator('main input')).to_have_count(0)
            page.screenshot(path=str(folder/'settings.png'),full_page=True)
        if route=='organization':expect(page.get_by_role('heading',name='快速检索')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),route
    page.goto(url+'/#/sources')
    expect(page.locator('a.record-title').first).to_be_visible()
    page.locator('a.record-title').nth(8).scroll_into_view_if_needed()
    scroll=page.evaluate('scrollY');page.locator('a.record-title').nth(8).click()
    expect(page.get_by_test_id('source-list-back')).to_be_visible();page.get_by_test_id('source-list-back').click()
    page.wait_for_function('(value)=>Math.abs(scrollY-value)<5',arg=scroll)
    for width,height in [(1366,768),(1920,1080),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        for route in ['reading','workbench','settings','organization','settings/ai','reading/browse']:
            page.goto(url+'/#/'+route);page.wait_for_load_state('networkidle')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(route,width)
        page.screenshot(path=str(folder/f'layout-{width}.png'))
    assert not errors,errors
    assert not mutations,mutations
    assert not external,external
    return {'routes':22,'viewports':[1366,1920,390],'page_errors':errors,'mutations':mutations,'external_requests':external}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path);args=parser.parse_args()
    folder=ROOT/'.cache/workspace-verification'/uuid4().hex;folder.mkdir(parents=True)
    root=folder/'portable'
    if args.bundle:shutil.copytree(args.bundle,root)
    else:root.mkdir()
    for key in list(os.environ):
        if key.startswith('MEMORY_OS_'):del os.environ[key]
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.cache/playwright')
    settings=Settings(_env_file=None,runtime_root=root,database_url='sqlite:///'+(root/'data/memory.db').as_posix(),sync_enabled=False,ai_enabled=False,rag_enabled=False)
    identifier=seed(root,settings)
    database=Database(settings.database_url);database.initialize()
    with database.session() as session:
        ContentService(session).create_knowledge({'title':'普通笔记验收','body':'独有检索词，普通正文。','summary':'普通笔记提要','tags':['普通'],'concepts':[]});session.commit()
    database.dispose()
    (root/'.env').write_text('MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=false\nMEMORY_OS_SYNC_ENABLED=false\n',encoding='utf-8')
    report={'status':'failed','real_model_calls':0,'frozen':bool(args.bundle)}
    server=FrozenDesktop(root,folder) if args.bundle else DesktopServer(settings)
    try:
        server.start();before=snapshot(root)
        with browser_environment(folder/'driver'),sync_playwright() as playwright:
            if args.bundle:browser,page=attach_window(playwright,server)
            else:
                browser=playwright.chromium.launch(channel='chromium',args=['--no-proxy-server']);page=browser.new_page(locale='zh-CN')
            report['checks']=checks(page,server.url,identifier,folder)
            assert snapshot(root)==before,'Browsing mutated synthetic records'
            if args.bundle:server.request_close();server.wait_closed()
            browser.close()
        report['status']='passed'
    except Exception:
        (folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        try:page.screenshot(path=str(folder/'failure.png'))
        except Exception:pass
    finally:
        server.stop();(folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(folder/'report.json')}));return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
