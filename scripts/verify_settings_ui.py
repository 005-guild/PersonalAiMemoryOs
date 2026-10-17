"""Settings acceptance in real Chromium, with all API requests intercepted."""

from http.server import ThreadingHTTPServer
import json
import os
from threading import Thread
import traceback
from uuid import uuid4

from playwright.sync_api import sync_playwright
from settings_ui_fixtures import SettingsUIAPI
from settings_ui_checks import check_roundtrip_and_busy, check_presets_keys_and_mobile
from settings_ui_error_checks import check_conflicts_and_errors, check_readonly_and_navigation, check_late_load, check_save_during_navigation
from v06_acceptance import browser_environment
from v06_editor_safeguards import AssetHandler
from verification_support import PROJECT_ROOT


def main():
    evidence = PROJECT_ROOT / '.cache/settings-ui' / uuid4().hex; evidence.mkdir(parents=True)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(PROJECT_ROOT / '.cache/playwright'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), AssetHandler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    report = {'api_mode': 'synthetic intercepted API; no personal files or model provider', 'real_model_calls': 0, 'cases': {}}
    try:
        with browser_environment(evidence / 'tmp'), sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=['--no-proxy-server'])
            try:
                cases = [('roundtrip_busy', check_roundtrip_and_busy), ('presets_keys_mobile', check_presets_keys_and_mobile),
                         ('conflicts_errors', check_conflicts_and_errors), ('readonly_dirty_navigation', check_readonly_and_navigation), ('late_load', check_late_load),
                         ('save_navigation_dialog', check_save_during_navigation)]
                for name, check in cases:
                    folder = evidence / name; folder.mkdir(); api = SettingsUIAPI()
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN', service_workers='block')
                    context.route('**/api/**', api.handle); context.route('**/health', api.handle)
                    page = context.new_page(); errors = []; external = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: external.append(request.url) if request.url.startswith('https://') else None)
                    try:
                        page.goto(f'http://127.0.0.1:{server.server_port}/#/settings')
                        result = check(page, api, folder)
                        assert not errors, errors
                        assert not external, external
                        assert all(call['path'] in ['/health', '/api/v1/settings/ai', '/api/v1/ui/knowledge', '/api/v1/prompt-templates'] for call in api.calls), api.calls
                        report['cases'][name] = {**result, 'page_errors': errors, 'external_requests': external}
                        print(name + ': passed', flush=True)
                    except Exception:
                        page.screenshot(path=str(folder / 'failure.png'), full_page=True)
                        (folder / 'failure.html').write_text(page.content(), encoding='utf-8')
                        report['cases'][name] = {'status': 'failed', 'page_errors': errors}; raise
                    finally:
                        # Never persist request bodies: they can contain synthetic password values.
                        (folder / 'requests.json').write_text(json.dumps(api.calls, ensure_ascii=False, indent=2), encoding='utf-8')
                        context.close()
            finally: browser.close()
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
        (evidence / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
