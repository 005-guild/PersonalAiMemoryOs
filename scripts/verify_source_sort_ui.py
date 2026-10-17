"""Offline Source sorting UI acceptance with an explicitly simulated API."""

from http.server import ThreadingHTTPServer
import json
import os
from threading import Thread
import traceback
from uuid import uuid4

from playwright.sync_api import sync_playwright
from source_sort_ui_fixtures import SortUIAPI
from source_sort_ui_checks import check_source_sorting
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT


def main():
    evidence = PROJECT_ROOT / '.cache/source-sort-ui' / uuid4().hex
    evidence.mkdir(parents=True)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(PROJECT_ROOT / '.cache/playwright'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), AssetHandler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    api = SortUIAPI()
    report = {'api_mode': 'synthetic intercepted API; no database or model provider', 'real_model_calls': 0}
    errors, external = [], []
    try:
        with browser_environment(evidence / 'tmp'), sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=['--no-proxy-server'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN', service_workers='block')
            context.route('**/api/**', api.handle); context.route('**/health', api.handle)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: external.append(request.url) if request.url.startswith('https://') else None)
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}/#/sources')
                report['sorting'] = check_source_sorting(page, api, evidence)
                assert not errors, errors
                assert not external, external
                report['status'] = 'passed'
            except Exception:
                page.screenshot(path=str(evidence / 'failure.png'), full_page=True)
                (evidence / 'failure.html').write_text(page.content(), encoding='utf-8')
                raise
            finally:
                context.close(); browser.close()
    except Exception as error:
        report.update(status='failed', error=str(error))
        (evidence / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        report.update(page_errors=errors, external_requests=external)
        (evidence / 'requests.json').write_text(json.dumps(api.calls, ensure_ascii=False, indent=2), encoding='utf-8')
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
