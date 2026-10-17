"""Real isolated FastAPI/SQLite/Chromium + local deterministic HTTP model acceptance."""
from http.server import ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4
import json
import os
import sys
import time
import traceback
import yaml

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.desktop.server import DesktopServer
from app.repositories.migrations import upgrade_database
from playwright.sync_api import expect, sync_playwright
from v06_acceptance import browser_environment
from v05_acceptance import storage_fingerprint
from v07_mock_server import Handler


def main():
    os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
    evidence=ROOT/'.cache/v07-local'/uuid4().hex;evidence.mkdir(parents=True)
    before=storage_fingerprint(); Handler.calls=[]
    model=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=model.serve_forever,daemon=True);thread.start()
    config=evidence/'config/ai-providers.yml';config.parent.mkdir()
    config.write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':{'local':{'label':'隔离模拟模型','enabled':True,'protocol':'openai_chat','base_url':f'http://127.0.0.1:{model.server_port}', 'model':'fixture-v07','auth':'none','response_format':'json_object','max_output_tokens':4096,'timeout_seconds':30}}},allow_unicode=True),encoding='utf-8')
    settings=Settings(_env_file=None,runtime_root=evidence,database_url='sqlite:///'+(evidence/'data/memory.db').as_posix(),knowledge_dir='knowledge',ai_enabled=True,rag_enabled=False,ai_keys={},ai_config_file='config/ai-providers.yml',embedding_config_file='config/absent.yml')
    upgrade_database(settings.database_url);server=DesktopServer(settings)
    report={'mode':'real isolated SQLite/FastAPI/Chromium + local deterministic HTTP provider','real_paid_model_calls':0,'formal_before':before}
    opener=build_opener(ProxyHandler({}))
    def request(method,path,body=None):
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        with opener.open(Request(server.url+path,method=method,data=data,headers={'Content-Type':'application/json'}),timeout=30) as response:
            raw=response.read();return json.loads(raw) if raw else None
    def wait_batch(identifier):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            value=request('GET','/api/v1/processing/batches/'+identifier)
            if value['status']=='completed':return value
            if value['status']=='paused':raise AssertionError(value)
            time.sleep(.1)
        raise AssertionError('batch did not finish')
    try:
        server.start()
        sources=[request('POST','/api/v1/sources',{'title':f'v07 合成来源 {index}', 'author':f'作者{index}','source_type':'manual','content':f'合成资料第 {index} 篇，用于验证准确引用、完整正文与多来源关联。\n不包含真实用户内容。'}) for index in range(1,4)]
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'.cache/playwright'))
        with browser_environment(evidence/'tmp'),sync_playwright() as playwright:
            browser=playwright.chromium.launch(args=['--no-proxy-server']);context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN');page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda item:external.append(item.url) if item.url.startswith('https://') else None)
            try:
                page.goto(server.url+'/#/processing')
                for source in sources:expect(page.locator(f'input[data-source-id="{source["id"]}"]')).to_be_visible();page.locator(f'input[data-source-id="{source["id"]}"]').check()
                page.get_by_test_id('processing-generate').click();expect(page.get_by_role('dialog')).to_contain_text('预计最多 3 次模型调用');page.get_by_role('dialog').get_by_role('button',name='开始生成').click()
                expect(page.get_by_test_id('processing-batch-detail')).to_be_visible()
                batch_id=page.url.split('batch_id=')[1];individual=wait_batch(batch_id)
                assert individual['counts']['ready']==3 and len(Handler.calls)==3
                assert request('GET','/api/v1/knowledge')['total']==0
                page.goto(server.url+'/#/processing/'+individual['items'][0]['run_id'])
                expect(page.get_by_test_id('processing-adopt')).to_be_enabled();expect(page.get_by_text('完整正文',exact=True)).to_be_visible()
                page.get_by_test_id('processing-adopt').click();expect(page.get_by_test_id('knowledge-body')).to_have_value('# 完整知识正文\n\n## 核心分析\n\n每篇资料有独立来源。\n\n## 实践结论\n\n保存版本与精确引用。')
                page.get_by_test_id('knowledge-body').fill(page.get_by_test_id('knowledge-body').input_value()+'\n\n本地编辑。');page.get_by_test_id('knowledge-save').click();page.wait_for_url('**/#/')
                page.goto(server.url+'/#/processing')
                for source in sources:page.locator(f'input[data-source-id="{source["id"]}"]').check()
                page.get_by_test_id('processing-mode').select_option('merged');page.get_by_test_id('processing-generate').click();expect(page.get_by_role('dialog')).to_contain_text('预计最多 1 次模型调用');page.get_by_role('dialog').get_by_role('button',name='开始生成').click()
                expect(page.get_by_test_id('processing-batch-detail')).to_be_visible();merged=wait_batch(page.url.split('batch_id=')[1])
                assert merged['counts']['ready']==1 and len(Handler.calls)==4
                page.goto(server.url+'/#/processing/'+merged['items'][0]['run_id']);expect(page.get_by_test_id('processing-adopt')).to_be_enabled();page.get_by_test_id('processing-adopt').click()
                expect(page.get_by_text('已选 3 / 20 篇',exact=True)).to_be_visible()
                note_id=page.url.split('/knowledge/')[1];note=request('GET','/api/v1/knowledge/'+note_id)
                assert note['source_ids']==[source['id'] for source in sources]
                page.get_by_test_id('knowledge-save').click();page.wait_for_url('**/#/')
                page.goto(server.url+'/#/settings');page.get_by_test_id('prompt-new').click();page.get_by_test_id('prompt-name').fill('真实数据库自定义模板');page.get_by_test_id('prompt-content').fill('请按事实、推论、实践建议组织中文正文。');page.get_by_test_id('prompt-save').click()
                expect(page.get_by_text('模板已保存，新生成任务立即可用；没有调用模型。')).to_be_visible()
                templates=request('GET','/api/v1/prompt-templates?limit=100')['items'];assert any(item['name']=='真实数据库自定义模板' for item in templates)
                assert len(Handler.calls)==4
                page.screenshot(path=str(evidence/'settings-1440.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(evidence/'settings-390.png'),full_page=True)
                assert not errors,errors;assert not external,external
                report.update(status='passed',individual_batch_id=individual['id'],merged_batch_id=merged['id'],local_mock_calls=Handler.calls,adopted_note_id=note_id,note_source_ids=note['source_ids'],page_errors=errors,external_requests=external,checks=['individual 3 sources/3 calls','preview creates zero notes','v2 full body preserved','adopt and edit returns overview','merged 3 sources/1 call','source_ids retained','no-change note save returns overview','Prompt create immediately persisted','390 layout'])
            except Exception:
                page.screenshot(path=str(evidence/'failure.png'),full_page=True);raise
            finally:context.close();browser.close()
    except Exception as error:
        report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        server.stop();model.shutdown();model.server_close();thread.join(timeout=3)
        report['formal_storage_unchanged']=before==storage_fingerprint()
        if not report['formal_storage_unchanged']:report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path);arguments=parser.parse_args()
    if arguments.bundle:
        from verify_v07_frozen import run
        raise SystemExit(run(arguments.bundle.resolve()))
    raise SystemExit(main())
