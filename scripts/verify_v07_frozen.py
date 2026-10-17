"""v0.7 real frozen EXE acceptance in an isolated copy, with a local synthetic model."""
import argparse
import ctypes
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from threading import Thread
import traceback
from uuid import uuid4
import yaml
from playwright.sync_api import expect, sync_playwright
from desktop_verification_support import FrozenDesktop, attach_window
from verification_support import PROJECT_ROOT, eventually
from v05_acceptance import storage_fingerprint
from v07_mock_server import Handler


class RestartedProcess:
    """Wait only for the new PID recorded by our owned portable application's restart."""
    def __init__(self,pid):
        self.pid=pid;self.returncode=None
        kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=ctypes.c_void_p
        self.handle=kernel.OpenProcess(0x100000|0x1000|1,False,pid)
        if not self.handle:raise OSError('Cannot inspect owned restarted process')
    def poll(self):
        code=ctypes.c_ulong();ctypes.windll.kernel32.GetExitCodeProcess(ctypes.c_void_p(self.handle),ctypes.byref(code))
        self.returncode=None if code.value==259 else code.value;return self.returncode
    def wait(self,timeout=40):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.poll() is not None:return self.returncode
            time.sleep(.05)
        raise subprocess.TimeoutExpired('owned restarted EXE',timeout)
    def kill(self):
        ctypes.windll.kernel32.TerminateProcess(ctypes.c_void_p(self.handle),1)


def run(bundle):
    evidence=PROJECT_ROOT/'.cache/v07-frozen'/uuid4().hex;evidence.mkdir(parents=True)
    portable=evidence/'中文 空格便携目录';shutil.copytree(bundle,portable)
    Handler.calls=[];model=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=model.serve_forever,daemon=True);thread.start()
    config=portable/'config/ai-providers.yml';config.parent.mkdir(exist_ok=True)
    config.write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':{'local':{'label':'隔离模拟模型','enabled':True,'protocol':'openai_chat','base_url':f'http://127.0.0.1:{model.server_port}','model':'fixture-v07','auth':'none','response_format':'json_object','max_output_tokens':4096,'timeout_seconds':30}}},allow_unicode=True),encoding='utf-8')
    (portable/'.env').write_text('MEMORY_OS_AI_ENABLED=true\nMEMORY_OS_RAG_ENABLED=false\nMEMORY_OS_AI_CONFIG_FILE=config/ai-providers.yml\n',encoding='utf-8')
    before=storage_fingerprint();app=FrozenDesktop(portable,evidence)
    report={'mode':'real frozen Windows EXE/WebView2/SQLite + isolated local deterministic model','bundle':str(bundle),'real_paid_calls':0}
    browser=None;page=None;errors=[]
    try:
        app.start();initial_pid=app.process.pid
        sources=[app.request('POST','/api/v1/sources',{'title':f'v07 合成来源 {index}','source_type':'manual','content':f'合成来源第 {index} 篇。精确引用来源及版本，不含真实用户内容。'}) for index in range(1,4)]
        def wait_batch(identifier):
            def completed():
                value=app.request('GET','/api/v1/processing/batches/'+identifier)
                if value['status']=='paused':raise AssertionError(value)
                return value if value['status']=='completed' else None
            return eventually(completed,timeout=40)
        with sync_playwright() as playwright:
            browser,page=attach_window(playwright,app)
            page.on('pageerror',lambda error:errors.append(str(error)))
            batches=[]
            for mode,calls in [('individual',3),('merged',1)]:
                page.goto(app.url+'/#/processing')
                for source in sources:page.locator(f'input[data-source-id="{source["id"]}"]').check()
                page.get_by_test_id('processing-mode').select_option(mode);page.get_by_test_id('processing-generate').click()
                expect(page.get_by_role('dialog')).to_contain_text(f'预计最多 {calls} 次模型调用');page.get_by_role('dialog').get_by_role('button',name='开始生成').click()
                expect(page.get_by_test_id('processing-batch-detail')).to_be_visible();batch=wait_batch(page.url.split('batch_id=')[1]);batches.append(batch)
                assert batch['counts']['ready']==calls
            assert len(Handler.calls)==4 and app.request('GET','/api/v1/knowledge')['total']==0
            page.goto(app.url+'/#/processing/'+batches[-1]['items'][0]['run_id']);expect(page.get_by_test_id('processing-adopt')).to_be_enabled();page.get_by_test_id('processing-adopt').click()
            expect(page.get_by_text('已选 3 / 20 篇',exact=True)).to_be_visible();note_id=page.url.split('/knowledge/')[1]
            page.get_by_test_id('knowledge-body').fill(page.get_by_test_id('knowledge-body').input_value()+'\n\nEXE 编辑保存。');page.get_by_test_id('knowledge-save').click();page.wait_for_url('**/#/')
            assert app.request('GET','/api/v1/knowledge/'+note_id)['source_ids']==[source['id'] for source in sources]
            page.goto(app.url+'/#/settings');page.get_by_test_id('prompt-new').click();page.get_by_test_id('prompt-name').fill('EXE 自定义模板');page.get_by_test_id('prompt-content').fill('请保留事实与推论之间的边界。');page.get_by_test_id('prompt-save').click();expect(page.get_by_text('模板已保存，新生成任务立即可用；没有调用模型。')).to_be_visible()
            page.get_by_test_id('ai-enabled').uncheck();page.get_by_test_id('ai-settings-save').click();expect(page.get_by_role('dialog')).to_be_visible();page.get_by_role('dialog').get_by_role('button',name='稍后',exact=True).click()
            assert app.process.pid==initial_pid and app.process.poll() is None
            assert app.request('GET','/api/v1/ai/profiles')['enabled'] is True
            page.get_by_test_id('ai-settings-save').click();page.get_by_role('dialog').get_by_role('button',name='现在重启',exact=True).click()
            old_url=app.url;old_process=app.process;old_process.wait(timeout=60)
            runtime=portable/'.cache/desktop/runtime.json'
            def restarted():
                if not runtime.exists():return None
                state=json.loads(runtime.read_text('utf-8'))
                return state if state.get('pid')!=initial_pid and state.get('status')=='running' else None
            state=eventually(restarted,timeout=100);app.runtime=state;app.url=state['url'].rstrip('/');app.process=RestartedProcess(state['pid'])
            assert app._port_closed(old_url)
            try:browser.close()
            except Exception:pass
            browser,page=attach_window(playwright,app);page.on('pageerror',lambda error:errors.append(str(error)))
            assert app.request('GET','/api/v1/ai/profiles')['enabled'] is False
            assert app.request('GET','/api/v1/knowledge/'+note_id)['source_ids']==[source['id'] for source in sources]
            duplicate=subprocess.Popen([str(portable/'PersonalAiMemoryOs.exe')],cwd=evidence,env=app.environment,creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.wait(timeout=20)==0 and app.process.poll() is None
            assert json.loads(runtime.read_text('utf-8'))['pid']==state['pid']
            page.goto(app.url+'/#/settings');expect(page.get_by_test_id('ai-settings-save')).to_be_visible();page.screenshot(path=str(evidence/'settings-after-restart.png'),full_page=True)
            assert any(item['name']=='EXE 自定义模板' for item in app.request('GET','/api/v1/prompt-templates?limit=100')['items'])
            assert not errors,errors;assert len(Handler.calls)==4
            app.request_close();app.wait_closed(timeout=60)
            report.update(status='passed',initial_pid=initial_pid,restarted_pid=state['pid'],mock_calls=Handler.calls,note_id=note_id,page_errors=errors,checks=['real frozen individual+merged batches','preview zero notes','v2 adoption multi-source','note save overview','template create','restart later retains active state','restart now drains and relaunches new PID','new configuration applied','data survives restart','duplicate activates same instance','graceful close releases port'])
    except Exception as error:
        report.update(status='failed',error=str(error),page_errors=errors);(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        if page:
            try:page.screenshot(path=str(evidence/'failure.png'),full_page=True)
            except Exception:pass
    finally:
        if browser:
            try:browser.close()
            except Exception:pass
        runtime=portable/'.cache/desktop/runtime.json'
        if app.process and app.process.poll() is not None and runtime.exists():
            state=json.loads(runtime.read_text('utf-8'))
            if state.get('status')=='running' and state.get('pid')!=app.process.pid:
                app.process=RestartedProcess(state['pid']);app.url=state['url'].rstrip('/')
        app.stop();model.shutdown();model.server_close();thread.join(timeout=3)
        report['formal_storage_unchanged']=before==storage_fingerprint()
        if not report['formal_storage_unchanged']:report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);args=parser.parse_args();raise SystemExit(run(args.bundle.resolve()))
