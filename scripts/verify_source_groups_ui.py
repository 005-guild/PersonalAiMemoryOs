"""Offline browser safeguards for grouped Source reading and numbered pagination."""

from http.server import ThreadingHTTPServer
import json
import os
from threading import Thread
import traceback
from uuid import uuid4

from playwright.sync_api import sync_playwright
from source_group_ui_fixtures import GroupUIAPI
from source_group_ui_checks import check_group_paging,check_group_reading,check_body_concurrency_and_dispose,check_conflict_restore_context
from source_group_route_checks import check_route_races_and_types
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT


def main():
    evidence=PROJECT_ROOT/'.cache/source-groups-ui'/uuid4().hex;evidence.mkdir(parents=True)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(PROJECT_ROOT/'.cache/playwright'))
    server=ThreadingHTTPServer(('127.0.0.1',0),AssetHandler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'api_mode':'synthetic intercepted APIs; no database or provider','real_model_calls':0,'cases':{}}
    try:
        with browser_environment(evidence/'tmp'),sync_playwright() as playwright:
            browser=playwright.chromium.launch(args=['--no-proxy-server'],downloads_path=str(evidence/'downloads'))
            try:
                for name,check in [('group_paging_context',check_group_paging),('safe_group_reading',check_group_reading),('concurrency_disposal',check_body_concurrency_and_dispose),('conflict_restore_context',check_conflict_restore_context),('hash_races_and_source_types',check_route_races_and_types)]:
                    folder=evidence/name;folder.mkdir();api=GroupUIAPI()
                    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',service_workers='block')
                    context.route('**/api/**',api.handle);context.route('**/health',api.handle)
                    page=context.new_page();errors=[];external=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.on('request',lambda request:external.append(request.url) if request.url.startswith('https://external.invalid') else None)
                    try:
                        page.goto(f'http://127.0.0.1:{server.server_port}/#/sources')
                        result=check(page,api,folder)
                        assert not errors,errors
                        assert not external,external
                        report['cases'][name]={**result,'page_errors':errors,'external_requests':external}
                        print(name+': passed',flush=True)
                    except Exception:
                        page.screenshot(path=str(folder/'failure.png'),full_page=True,animations='disabled')
                        (folder/'failure.html').write_text(page.content(),encoding='utf-8')
                        report['cases'][name]={'status':'failed','page_errors':errors};raise
                    finally:
                        (folder/'requests.json').write_text(json.dumps(api.calls,ensure_ascii=False,indent=2),encoding='utf-8');context.close()
            finally:browser.close()
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8');print(str(error),flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
