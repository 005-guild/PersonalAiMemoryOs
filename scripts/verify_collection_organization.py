"""Offline browser acceptance with synthetic articles and an injected model stub."""
import json
import os
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_collection_organization import Model, article, PNG
from app.config import Settings
from app.agents.configuration import AIProfile,ResolvedProfile
from app.repositories.migrations import upgrade_database
from app.desktop.server import DesktopServer
from v06_acceptance import browser_environment
from playwright.sync_api import expect,sync_playwright


def main():
    evidence=ROOT/'.cache/collection-browser'/uuid4().hex
    evidence.mkdir(parents=True)
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.cache/playwright')
    for key in list(os.environ):
        if key.startswith('MEMORY_OS_'):del os.environ[key]
    source=evidence/'articles';output=evidence/'organized'
    for n in range(1,7):article(source,n)
    for n in range(7,9):article(source,n,'长文的完整证据需要保留。\n'*2000)
    (source/'images').mkdir();(source/'images/p.png').write_bytes(PNG)
    for n in range(9,11):article(source,n,'![图](images/p.png)')
    url='sqlite:///'+(evidence/'data/memory.db').as_posix()
    upgrade_database(url)
    settings=Settings(_env_file=None,runtime_root=evidence,database_url=url,sync_enabled=True,ai_enabled=False,rag_enabled=False)
    server=DesktopServer(settings)
    model=Model();profile=AIProfile(protocol='openai_chat',base_url='https://api.deepseek.com',model='deepseek-flash')
    organization=server.app.state.organization
    organization.calls.client=model
    openai=AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol')
    profiles={'deepseek':profile,'openai-responses':openai}
    organization.calls.registry=SimpleNamespace(resolve=lambda identifier:ResolvedProfile(identifier,profiles[identifier],None,'synthetic'),profiles=profiles)
    async def count(*args,**kwargs):return 100
    model.count_input_tokens=count
    report={'status':'failed','real_model_calls':0}
    try:
        server.start()
        with browser_environment(evidence/'driver'),sync_playwright() as p:
            browser=p.chromium.launch(channel='chromium',args=['--no-proxy-server'])
            page=browser.new_page(viewport={'width':1440,'height':1100},locale='zh-CN')
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(server.url+'/#/organization/config')
            page.get_by_label('原文目录',exact=True).fill(str(source))
            page.get_by_label('整理库目录',exact=True).fill(str(output))
            page.get_by_role('button',name='保存设置',exact=True).click()
            expect(page.get_by_text('操作已保存，进度会自动刷新。',exact=True)).to_be_visible()
            page.goto(server.url+'/#/organization')
            expect(page.locator('[data-action=all]')).to_be_disabled()
            expect(page.locator('[data-action=all]')).not_to_be_visible()
            page.get_by_role('button',name='生成 10 篇样本',exact=True).click()
            from verification_support import eventually
            eventually(lambda:any(j['status']=='completed' for j in organization.store.read()['jobs']),timeout=60)
            page.locator('a.entry-card[href="#/organization/review"]').click()
            expect(page.get_by_role('button',name='确认这批样本',exact=True)).to_be_enabled(timeout=60000)
            assert not output.exists()
            page.screenshot(path=str(evidence/'sample-review.png'),full_page=True)
            count=len(model.calls)
            page.get_by_role('button',name='确认这批样本',exact=True).click()
            page.goto(server.url+'/#/organization')
            expect(page.get_by_role('button',name='开始全量整理',exact=True)).to_be_enabled()
            page.get_by_role('button',name='开始全量整理',exact=True).click()
            expect(page.get_by_text('已入库 10',exact=True)).to_be_visible(timeout=60000)
            assert len(model.calls)==count
            page.goto(server.url+'/#/search?mode=keyword&q=实践')
            expect(page.get_by_role('heading',name='找到 10 篇文章',exact=True)).to_be_visible()
            page.screenshot(path=str(evidence/'search.png'),full_page=True)
            assert len(list(output.glob('*/*/*.md')))==10
            page.goto(server.url+'/#/organization/config')
            page.get_by_label('AI 配置名称',exact=True).fill('openai-responses')
            page.get_by_role('button',name='切换模型并保留样式确认',exact=True).click()
            expect(page.get_by_text('操作已保存，进度会自动刷新。',exact=True)).to_be_visible()
            expect(page.get_by_label('AI 配置名称',exact=True)).to_have_value('openai-responses')
            page.goto(server.url+'/#/organization')
            expect(page.get_by_role('button',name='开始全量整理',exact=True)).to_be_enabled()
            article(source,11)
            page.get_by_role('button',name='扫描原文',exact=True).click()
            expect(page.get_by_text('发现 11 篇；长文 2 篇；需识图 2 篇。',exact=True)).to_be_visible()
            page.get_by_role('button',name='开始全量整理',exact=True).click()
            expect(page.get_by_text('已入库 11',exact=True)).to_be_visible(timeout=60000)
            assert len(model.calls)==count+1
            assert len(list(output.glob('*/*/*.md')))==11
            assert not errors,errors
            report.update(status='passed',sample_count=10,synthetic_requests=count,
                          checks=['sample_gate','long_document','images','publication_cache','short_chinese_search','explicit_openai_switch','new_items_only','no_page_errors'])
            browser.close()
    except Exception:
        (evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        (evidence/'state.json').write_text(json.dumps(organization.store.read(),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        server.stop()
        (evidence/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
