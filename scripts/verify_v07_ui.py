"""Repeatable Chromium checks for v0.7 UI with synthetic API interception."""
from http.server import ThreadingHTTPServer
from threading import Thread
from uuid import uuid4
import json
import os
import traceback
from playwright.sync_api import sync_playwright
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT
from v07_ui_fixtures import V07UIAPI, uid
from v07_ui_checks import check_selection_and_batch, check_prompt_management, check_note_sources, check_restore_sources, check_restart_choice, check_selection_limit_and_failure, check_preview_race, check_initial_source_dirty


def main():
    evidence=PROJECT_ROOT/'.cache/v07-ui'/uuid4().hex; evidence.mkdir(parents=True)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(PROJECT_ROOT/'.cache/playwright'))
    server=ThreadingHTTPServer(('127.0.0.1',0),AssetHandler); thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'api_mode':'synthetic intercepted API; real Chromium; no personal data or model calls','cases':{}}
    cases=[('selection_batch','processing',check_selection_and_batch),('prompt_management','settings',check_prompt_management),
           ('note_multi_sources',f'knowledge/{uid(200)}',check_note_sources),('restore_multi_sources',f'knowledge/{uid(200)}',check_restore_sources),('restart_choices','settings',check_restart_choice),('selection_limit_failure','processing',check_selection_limit_and_failure),('preview_route_race','processing',check_preview_race),('initial_source_dirty',f'processing?source_id={uid(1)}',check_initial_source_dirty)]
    try:
        with browser_environment(evidence/'tmp'),sync_playwright() as playwright:
            browser=playwright.chromium.launch(args=['--no-proxy-server'])
            try:
                for name,path,check in cases:
                    folder=evidence/name;folder.mkdir();fixture=V07UIAPI()
                    if name=='restore_multi_sources':fixture.notes[uid(200)]['deleted_at']='2026-01-01T00:00:00Z';fixture.sources[1]['deleted_at']='2026-01-01T00:00:00Z'
                    if name=='initial_source_dirty':fixture.hold_preview=True
                    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',service_workers='block');context.route('**/api/**',fixture.handle);context.route('**/health',fixture.handle)
                    page=context.new_page();errors=[];external=[]
                    page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda request:external.append(request.url) if request.url.startswith('https://') else None)
                    try:
                        page.goto(f'http://127.0.0.1:{server.server_port}/#/{path}')
                        result=check(page,fixture,folder)
                        assert not errors,errors;assert not external,external
                        report['cases'][name]={'status':'passed',**result,'page_errors':errors,'external_requests':external}
                        print(name+': passed',flush=True)
                    except Exception:
                        page.screenshot(path=str(folder/'failure.png'),full_page=True);(folder/'failure.html').write_text(page.content(),encoding='utf-8');raise
                    finally:context.close()
            finally:browser.close()
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3);(evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
