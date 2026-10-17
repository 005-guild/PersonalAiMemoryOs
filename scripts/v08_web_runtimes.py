"""Isolated Docker and frozen EXE runners for the shared v0.8 browser checks."""
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
import json
import os
import shutil
import traceback
from uuid import uuid4
import yaml
from playwright.sync_api import sync_playwright
from v06_acceptance import browser_environment
from v05_acceptance import Runtime,storage_fingerprint
from verification_support import PROJECT_ROOT
from v08_web_checks import seed,run_checks
from v08_web_mock_server import Handler


class BrowserDocker(Runtime):
    def command(self,arguments,**kwargs):
        if self.manifest.exists()and not getattr(self,'adjusted',False):
            document=json.loads(self.manifest.read_text(encoding='utf-8'));environment=document['services']['api']['environment']
            environment.update(MEMORY_OS_RAG_ENABLED='false',MEMORY_OS_CONFIGURATION_READ_ONLY='true')
            self.manifest.write_text(json.dumps(document),encoding='utf-8');self.adjusted=True
        return super().command(arguments,**kwargs)


def run_docker(image):
    evidence=PROJECT_ROOT/'.cache/v08-web-docker'/uuid4().hex;evidence.mkdir(parents=True);before=storage_fingerprint()
    runtime=BrowserDocker(evidence/('runtime-'+uuid4().hex[:12]),'docker',image,mock_script=PROJECT_ROOT/'scripts/v08_web_mock_server.py');report={'mode':'real isolated Docker/FastAPI/Chromium; synthetic local models','real_paid_calls':0}
    try:
        runtime.start()
        import urllib.request
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(method,path,body=None):
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
            with opener.open(urllib.request.Request(runtime.base_url+path,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=40)as response:
                raw=response.read();return json.loads(raw)if raw else None
        seeded=seed(request);os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(PROJECT_ROOT/'.cache/playwright'))
        with browser_environment(evidence/'tmp'),sync_playwright()as playwright:
            browser=playwright.chromium.launch(args=['--no-proxy-server']);context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN');page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                checks=run_checks(page,runtime.base_url,request,evidence,seeded,read_only=True);assert not errors,errors
                records=[json.loads(line)for line in (runtime.workspace/'mock-requests.jsonl').read_text(encoding='utf-8').splitlines()]
                assert sum(item['endpoint']=='chat'for item in records)==1 and sum(item['endpoint']=='embeddings'for item in records)==1
                report.update(status='passed',checks=checks,page_errors=errors,generation_calls=1,embedding_calls=1)
            except Exception:page.screenshot(path=str(evidence/'failure.png'),full_page=True);raise
            finally:context.close();browser.close()
    except Exception as error:report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        try:runtime.stop()
        except Exception as error:report.update(status='failed',cleanup_error=type(error).__name__)
        report['formal_storage_unchanged']=before==storage_fingerprint()
        if not report['formal_storage_unchanged']:report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True);return 0 if report['status']=='passed'else 1


def run_frozen(bundle):
    from desktop_verification_support import FrozenDesktop,attach_window
    evidence=PROJECT_ROOT/'.cache/v08-web-frozen'/uuid4().hex;evidence.mkdir(parents=True);portable=evidence/'中文 固定目录验收';shutil.copytree(bundle,portable);before=storage_fingerprint()
    Handler.calls=[];Handler.embedding_calls=0;model=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=model.serve_forever,daemon=True);thread.start()
    directory=portable/'config';directory.mkdir(exist_ok=True);base=f'http://127.0.0.1:{model.server_port}'
    for name,profile in [('ai-providers.yml',{'label':'隔离生成','enabled':True,'protocol':'openai_chat','base_url':base,'model':'fixture-v08','auth':'none','response_format':'json_object','max_output_tokens':4096,'timeout_seconds':30}),
                         ('embedding-providers.yml',{'label':'隔离向量','enabled':True,'protocol':'openai_embeddings','base_url':base,'model':'fixture-v08-embedding','auth':'none','dimension':4})]:
        profiles={'local':profile,**{f'local_{index}':{**profile,'label':f'分页配置 {index}'}for index in range(1,22)}}
        (directory/name).write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':profiles},allow_unicode=True,sort_keys=False),encoding='utf-8')
    (portable/'.env').write_text('MEMORY_OS_AI_ENABLED=true\nMEMORY_OS_RAG_ENABLED=false\nMEMORY_OS_AI_CONFIG_FILE=config/ai-providers.yml\nMEMORY_OS_EMBEDDING_CONFIG_FILE=config/embedding-providers.yml\n',encoding='utf-8')
    app=FrozenDesktop(portable,evidence);report={'mode':'real frozen Windows EXE/WebView2 with isolated models','bundle':str(bundle),'real_paid_calls':0};browser=None;page=None
    try:
        app.start();seeded=seed(app.request)
        with sync_playwright()as playwright:
            browser,page=attach_window(playwright,app);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            downloads=portable/'exports';downloads.mkdir(exist_ok=True)
            browser.new_browser_cdp_session().send('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(downloads),'eventsEnabled':True})
            checks=run_checks(page,app.url,app.request,evidence,seeded,desktop_root=portable);assert not errors,errors
            assert len(Handler.calls)==1 and Handler.embedding_calls==1
            from verification_support import eventually
            from verify_v07_frozen import RestartedProcess
            import subprocess
            restarts=[];page.on('request',lambda item:restarts.append(item.post_data_json)if item.url.endswith('/api/v1/desktop/restart')else None)
            old_pid=app.process.pid;old_url=app.url;old_process=app.process
            page.goto(app.url+'/#/settings');page.get_by_test_id('rag-settings-save').click()
            page.get_by_role('dialog').get_by_role('button',name='现在重启',exact=True).click();old_process.wait(timeout=90)
            state_file=portable/'.cache/desktop/runtime.json'
            def restarted():
                if not state_file.exists():return None
                state=json.loads(state_file.read_text(encoding='utf-8'));return state if state.get('pid')!=old_pid and state.get('status')=='running'else None
            state=eventually(restarted,timeout=100);app.runtime=state;app.url=state['url'].rstrip('/');app.process=RestartedProcess(state['pid']);assert app._port_closed(old_url)
            report['restart']={'scope':'rag','old_pid':old_pid,'new_pid':state['pid'],'old_port_released':True}
            try:browser.close()
            except Exception:pass
            browser,page=attach_window(playwright,app);page.on('pageerror',lambda error:errors.append(str(error)))
            active=app.request('GET','/api/v1/settings/rag');assert not active['active']['enabled']and not active['restart_required']
            assert active['profiles'][0]['label']=='浏览器配置保存（隔离）'
            assert len(restarts)==1 and restarts[0]['scope']=='rag'
            assert len(Handler.calls)==1 and Handler.embedding_calls==1
            duplicate=subprocess.Popen([str(portable/'PersonalAiMemoryOs.exe')],cwd=evidence,env=app.environment,creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.wait(timeout=20)==0 and app.process.poll()is None
            assert app.request('GET','/api/v1/ui/drafts?state=adopted')['total']==1
            assert json.loads(state_file.read_text(encoding='utf-8'))['pid']==state['pid']
            checks.extend(['RAG restart later leaves current process active','RAG scope protected restart now creates new PID and releases old port','saved RAG-off configuration actually active after restart','single-instance handoff and data retained'])
            app.request_close();app.wait_closed(timeout=60);report.update(status='passed',checks=checks,page_errors=errors,generation_calls=len(Handler.calls),embedding_calls=Handler.embedding_calls)
    except Exception as error:
        report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        if page:
            try:page.screenshot(path=str(evidence/'failure.png'),full_page=True)
            except Exception:pass
    finally:
        if browser:
            try:browser.close()
            except Exception:pass
        state_file=portable/'.cache/desktop/runtime.json'
        if app.process and app.process.poll()is not None and state_file.exists():
            state=json.loads(state_file.read_text(encoding='utf-8'))
            if state.get('status')=='running'and state.get('pid')!=app.process.pid:
                from verify_v07_frozen import RestartedProcess
                app.process=RestartedProcess(state['pid']);app.url=state['url'].rstrip('/')
        app.stop();model.shutdown();model.server_close();thread.join(timeout=3);report['formal_storage_unchanged']=before==storage_fingerprint()
        if not report['formal_storage_unchanged']:report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True);return 0 if report['status']=='passed'else 1
