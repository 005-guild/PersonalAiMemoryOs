"""Isolated actual EXE reuse of shared local services: startup, read-only probe, protected restart."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
from urllib.error import HTTPError
from urllib.request import ProxyHandler,Request,build_opener
from uuid import uuid4
import winreg
import yaml

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from desktop_verification_support import FrozenDesktop,attach_window
from verification_support import eventually
from verify_v07_frozen import RestartedProcess
from v05_acceptance import storage_fingerprint
from playwright.sync_api import sync_playwright,expect

REVISION=None
OPENER=build_opener(ProxyHandler({}))
def http(method,url,body=None,headers=None):
    request=Request(url,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with OPENER.open(request,timeout=40) as response:return response.status,json.load(response)
    except HTTPError as error:return error.code,json.load(error)
def containers(docker):
    result=subprocess.run([docker,'ps','--format','{{json .}}'],check=True,capture_output=True,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    return {value['Names']:value['ID'] for line in result.stdout.splitlines() if (value:=json.loads(line))}
def calls():
    text=(ROOT/'.cache/ollama/server.stdout.log').read_text('utf-8',errors='replace')
    return {path:len(re.findall(r'POST\s+"'+re.escape(path)+r'"',text)) for path in ['/v1/embeddings','/api/embed','/api/embeddings','/api/generate','/api/chat','/v1/chat/completions']}
def collections():return sorted(item['name'] for item in http('GET','http://127.0.0.1:6333/collections')[1]['result']['collections'])
def own_cleanup(database):
    deleted=[]
    if not database.exists():return deleted
    with sqlite3.connect(database) as connection:
        assert connection.execute('select count(*) from knowledge').fetchone()[0]==0
        assert connection.execute('select count(*) from rag_index_jobs').fetchone()[0]==0
        rows=connection.execute('select id,owner_id,collection from rag_index_generations').fetchall()
    for identifier,owner,name in rows:
        status,value=http('GET','http://127.0.0.1:6333/collections/'+name)
        if status==404:continue
        metadata=value['result']['config']['metadata']
        assert metadata=={'application':'personal-ai-memory-os','generation_id':identifier,'owner_id':owner},metadata
        assert http('DELETE','http://127.0.0.1:6333/collections/'+name)[0]==200
        deleted.append(name)
    return deleted

def run(bundle):
    global REVISION
    models=http('GET','http://127.0.0.1:11434/api/tags')[1]['models']
    REVISION=next(item['digest'] for item in models if item['name']=='bge-m3:latest')
    evidence=ROOT/'.cache/desktop-local-startup'/uuid4().hex;evidence.mkdir(parents=True)
    portable=evidence/'中文 空格自动启动便携副本';shutil.copytree(bundle,portable)
    config=portable/'config';config.mkdir(exist_ok=True)
    (config/'local-rag-startup.json').write_text(json.dumps({'schema_version':1,'enabled':True,'project_root':str(ROOT)},ensure_ascii=False),encoding='utf-8')
    (config/'embedding-providers.yml').write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':{'local':{'label':'本地 BGE-M3','enabled':True,'protocol':'openai_embeddings','base_url':'http://127.0.0.1:11434/v1','model':'bge-m3','model_revision':REVISION,'dimension':1024,'auth':'none','batch_size':8,'timeout_seconds':60}}},allow_unicode=True),encoding='utf-8')
    (portable/'.env').write_text('MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=true\nMEMORY_OS_EMBEDDING_CONFIG_FILE=config/embedding-providers.yml\nMEMORY_OS_RAG_QDRANT_URL=http://127.0.0.1:6333\n',encoding='utf-8')
    files=[portable/'.env',config/'embedding-providers.yml',config/'local-rag-startup.json']
    configuration_hashes={str(path.relative_to(portable)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    docker=shutil.which('docker.exe');assert docker
    proxy_key=winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
    proxy_enabled=bool(winreg.QueryValueEx(proxy_key,'ProxyEnable')[0]);winreg.CloseKey(proxy_key)
    before={'containers':containers(docker),'calls':calls(),'collections':collections(),'ollama':json.loads((ROOT/'.cache/ollama/service.json').read_text('utf-8-sig')),'formal':storage_fingerprint()}
    models=http('GET','http://127.0.0.1:11434/api/tags')[1]['models']
    model=next(item for item in models if item['name']=='bge-m3:latest')
    assert model['digest']==REVISION, 'Configured model revision differs from installed BGE-M3'
    assert before['ollama']['pid']>0
    app=FrozenDesktop(portable,evidence)
    app.environment={key:value for key,value in app.environment.items() if key.upper() not in {'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'}}
    app.environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')+os.pathsep+str(Path(docker).parent)
    report={'mode':'actual isolated frozen EXE, real existing Ollama/Qdrant, Windows proxy enabled; zero model calls','bundle':str(bundle),'system_proxy_enabled':proxy_enabled,'input_proxy_environment_removed':True,'input_path':app.environment['PATH']}
    browser=None;page=None;errors=[]
    try:
        app.start();old_pid=app.process.pid;old_url=app.url;old_process=app.process
        def ready():
            status=app.request('GET','/api/v1/rag/index/status')
            return status if status.get('generation',{}).get('status')=='ready' and not status.get('last_error') else None
        index=eventually(ready,timeout=40)
        assert app.request('GET','/api/v1/ui/knowledge?state=all')['total']==0
        assert app.request('GET','/api/v1/ai/profiles')['enabled'] is False
        settings=app.request('GET','/api/v1/settings/rag');assert settings['active']['enabled'] and settings['enabled']
        headers={'Origin':app.url,'X-Configuration-Token':settings['csrf_token']}
        code,probe=http('POST',app.url+'/api/v1/settings/rag/test',{'expected_revision':settings['revision'],'target':'qdrant'},headers)
        assert code==200 and probe=={'target':'qdrant','status':'ok','read_only':True},(code,probe)
        duplicate=subprocess.Popen([str(portable/'PersonalAiMemoryOs.exe')],cwd=evidence,env=app.environment,creationflags=subprocess.CREATE_NO_WINDOW)
        assert duplicate.wait(timeout=20)==0 and app.process.poll() is None
        runtime=portable/'.cache/desktop/runtime.json';assert json.loads(runtime.read_text('utf-8'))['pid']==old_pid
        with sync_playwright() as playwright:
            browser,page=attach_window(playwright,app);page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(app.url+'/#/settings');expect(page.get_by_test_id('rag-enabled')).to_be_checked();page.screenshot(path=str(evidence/'settings-before-restart.png'),full_page=True)
            payload={'scope':'rag','expected_revision':settings['revision']}
            code,_=http('POST',app.url+'/api/v1/desktop/restart',payload,{'Origin':app.url,'X-Configuration-Token':'invalid-test-token'})
            assert code==403 and app.process.poll() is None
            code,result=http('POST',app.url+'/api/v1/desktop/restart',payload,headers);assert code==202 and result['status']=='restarting'
            assert old_process.wait(timeout=90)==0
            def restarted():
                state=json.loads(runtime.read_text('utf-8'));return state if state.get('pid')!=old_pid and state.get('status')=='running' else None
            state=eventually(restarted,timeout=100);app.runtime=state;app.url=state['url'].rstrip('/');app.process=RestartedProcess(state['pid']);assert app._port_closed(old_url)
            try:browser.close()
            except Exception:pass
            browser,page=attach_window(playwright,app);page.on('pageerror',lambda error:errors.append(str(error)))
            index=eventually(ready,timeout=40);active=app.request('GET','/api/v1/settings/rag');assert active['active']['enabled']
            profile=next(item for item in active['profiles'] if item['id']=='local');assert profile['model_revision']==REVISION and profile['dimension']==1024
            assert configuration_hashes=={str(path.relative_to(portable)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
            page.goto(app.url+'/#/settings');expect(page.get_by_test_id('rag-enabled')).to_be_checked();page.screenshot(path=str(evidence/'settings-after-restart.png'),full_page=True)
            assert not errors,errors
            app.request_close();app.wait_closed(timeout=60)
            log=(portable/'logs/memory-os.log').read_text('utf-8');helper=(portable/'logs/local-rag-startup.log').read_text('utf-8',errors='replace')
            assert log.count('Local RAG services are ready.')==2
            assert helper.count('Qdrant 1.19.2 ready')==2
            report.update(status='passed',old_pid=old_pid,new_pid=state['pid'],read_only_qdrant_probe=probe,invalid_restart_status=403,restart_scope='rag',configuration_retained=True,parent_proxy_bypass_proved_by_probe=True,services_ready_log_count=2,page_errors=errors,model_calls=0,old_and_final_port_released=True)
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
            if state.get('status')=='running' and state.get('pid')!=app.process.pid:app.process=RestartedProcess(state['pid']);app.url=state['url'].rstrip('/')
        app.stop()
        report['owned_collections_deleted']=own_cleanup(portable/'data/memory.db')
        after={'containers':containers(docker),'calls':calls(),'collections':collections(),'ollama':json.loads((ROOT/'.cache/ollama/service.json').read_text('utf-8-sig')),'formal':storage_fingerprint()}
        report['shared_container_ids_unchanged']=before['containers']==after['containers'];report['ollama_record_unchanged']=before['ollama']==after['ollama'];report['model_request_counts_before']=before['calls'];report['model_request_counts_after']=after['calls'];report['shared_collections_unchanged']=before['collections']==after['collections'];report['formal_storage_unchanged']=before['formal']==after['formal']
        if not (report['shared_container_ids_unchanged'] and report['ollama_record_unchanged'] and before['calls']==after['calls'] and report['shared_collections_unchanged'] and report['formal_storage_unchanged']):report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True);return 0 if report['status']=='passed' else 1

if __name__=='__main__':
    if sys.platform != 'win32': raise SystemExit('Windows, WebView2, clean bundle and running local services are required.')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);args=parser.parse_args();
    from build_desktop import inspect_bundle
    inspect_bundle(args.bundle.resolve())
    raise SystemExit(run(args.bundle.resolve()))
