"""Chromium Markdown/JSON import safeguards with explicitly mocked API responses."""

from http.server import ThreadingHTTPServer
import json
import os
from threading import Thread
import traceback
from uuid import uuid4

from playwright.sync_api import sync_playwright

from markdown_ui_fixtures import MarkdownUIAPI
from markdown_ui_checks import check_large_directory, check_read_errors_and_partial, check_selection_races, check_request_limits, check_legacy_json
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT


def main():
    evidence = PROJECT_ROOT / '.cache/markdown-ui-validation' / uuid4().hex
    evidence.mkdir(parents=True)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(PROJECT_ROOT / '.cache/playwright'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), AssetHandler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    report = {'api_mode':'synthetic browser interception; no backend database', 'real_model_calls':0, 'cases':{}}
    try:
        with browser_environment(evidence/'tmp'), sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=['--no-proxy-server'], downloads_path=str(evidence/'downloads'))
            try:
                for name, check in [('large_directory',check_large_directory), ('read_errors_partial_xss',check_read_errors_and_partial),
                                    ('selection_races',check_selection_races), ('limits',check_request_limits), ('legacy_json',check_legacy_json)]:
                    folder = evidence/name;folder.mkdir()
                    api = MarkdownUIAPI()
                    context = browser.new_context(viewport={'width':1440,'height':1000}, locale='zh-CN', service_workers='block')
                    context.route('**/api/**',api.handle);context.route('**/health',api.handle)
                    page = context.new_page();errors=[]
                    page.on('pageerror',lambda error: errors.append(str(error)))
                    try:
                        page.goto(f'http://127.0.0.1:{server.server_port}/#/imports')
                        value=check(page,api,folder)
                        assert not errors,errors
                        report['cases'][name]={**value,'page_errors':errors}
                        print(name+': passed',flush=True)
                    except Exception:
                        page.screenshot(path=str(folder/'failure.png'),full_page=True,animations='disabled')
                        (folder/'failure.html').write_text(page.content(),encoding='utf-8')
                        report['cases'][name]={'status':'failed','page_errors':errors}
                        raise
                    finally:
                        (folder/'requests.json').write_text(json.dumps([{'url':item['url'],'bytes':len(item['bytes'])} for item in api.calls],indent=2),encoding='utf-8')
                        context.close()
            finally:browser.close()
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=str(error));(evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print('Markdown UI validation failed: '+str(error),flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
