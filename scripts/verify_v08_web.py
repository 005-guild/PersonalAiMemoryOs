"""v0.8 isolated real SQLite/FastAPI/Chromium acceptance; no paid model calls."""
from http.server import ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4
import json
import os
import sys
import traceback
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.desktop.server import DesktopServer
from app.repositories.migrations import upgrade_database
from playwright.sync_api import sync_playwright
from v06_acceptance import browser_environment
from v05_acceptance import storage_fingerprint
from v07_mock_server import Handler as GenerationHandler
from v08_web_checks import seed,run_checks

class Handler(GenerationHandler):
    embedding_calls=0
    def do_POST(self):
        if self.path!='/embeddings':return super().do_POST()
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));type(self).embedding_calls+=1
        raw=json.dumps({'data':[{'index':index,'embedding':[1.,2.,3.,4.]}for index,_ in enumerate(payload['input'])],'usage':{'total_tokens':4}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def main():
    os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
    evidence=ROOT/'.cache/v08-web'/uuid4().hex;evidence.mkdir(parents=True);before=storage_fingerprint();Handler.calls=[]
    model=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=model.serve_forever,daemon=True);thread.start()
    config=evidence/'config';config.mkdir();base=f'http://127.0.0.1:{model.server_port}'
    (config/'ai-providers.yml').write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':{'local':{'label':'隔离模型','enabled':True,'protocol':'openai_chat','base_url':base,'model':'fixture-v08','auth':'none','response_format':'json_object','max_output_tokens':4096,'timeout_seconds':30}}},allow_unicode=True),encoding='utf-8')
    (config/'embedding-providers.yml').write_text(yaml.safe_dump({'schema_version':1,'default_profile':'local','profiles':{'local':{'label':'隔离向量','enabled':True,'protocol':'openai_embeddings','base_url':base,'model':'fixture-v08-embedding','auth':'none','dimension':4}}},allow_unicode=True),encoding='utf-8')
    for filename in ['ai-providers.yml','embedding-providers.yml']:
        path=config/filename;document=yaml.safe_load(path.read_text(encoding='utf-8'));original=document['profiles']['local']
        document['profiles'].update({f'local_{index}':{**original,'label':f'分页配置 {index}'}for index in range(1,22)})
        path.write_text(yaml.safe_dump(document,allow_unicode=True,sort_keys=False),encoding='utf-8')
    settings=Settings(_env_file=None,runtime_root=evidence,database_url='sqlite:///'+(evidence/'data/memory.db').as_posix(),knowledge_dir='knowledge',ai_enabled=True,rag_enabled=False,ai_keys={},ai_config_file='config/ai-providers.yml',embedding_config_file='config/embedding-providers.yml')
    upgrade_database(settings.database_url);server=DesktopServer(settings);opener=build_opener(ProxyHandler({}))
    def request(method,path,body=None):
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        with opener.open(Request(server.url+path,method=method,data=data,headers={'Content-Type':'application/json'}),timeout=30)as response:
            raw=response.read();return json.loads(raw)if raw else None
    report={'mode':'real isolated SQLite/FastAPI/Chromium and deterministic local model','real_model_calls':0}
    try:
        server.start();seeded=seed(request);os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'.cache/playwright'))
        with browser_environment(evidence/'tmp'),sync_playwright()as playwright:
            browser=playwright.chromium.launch(args=['--no-proxy-server']);context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN');page=context.new_page();errors=[];external=[]
            page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda item:external.append(item.url)if item.url.startswith('https://')else None)
            try:
                checks=run_checks(page,server.url,request,evidence,seeded)
                assert not errors,errors;assert not external,external;assert len(Handler.calls)==1;assert Handler.embedding_calls==1
                report.update(status='passed',checks=checks,page_errors=errors,external_requests=external,generation_calls=len(Handler.calls),embedding_calls=Handler.embedding_calls)
            except Exception:
                page.screenshot(path=str(evidence/'failure.png'),full_page=True);(evidence/'failure.html').write_text(page.content(),encoding='utf-8');raise
            finally:context.close();browser.close()
    except Exception as error:report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        server.stop();model.shutdown();model.server_close();thread.join(timeout=3);report['formal_storage_unchanged']=before==storage_fingerprint()
        if not report['formal_storage_unchanged']:report['status']='failed'
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True);return 0 if report['status']=='passed'else 1
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mode',choices=['local','docker','desktop'],default='local');parser.add_argument('--image',default='memory-os-v08-validation:latest');parser.add_argument('--bundle',type=Path);args=parser.parse_args()
    if args.mode=='local':raise SystemExit(main())
    from v08_web_runtimes import run_docker,run_frozen
    if args.mode=='desktop'and not args.bundle:parser.error('--bundle is required for desktop')
    raise SystemExit(run_docker(args.image)if args.mode=='docker'else run_frozen(args.bundle.resolve()))
