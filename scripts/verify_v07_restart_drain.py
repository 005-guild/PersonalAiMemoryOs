"""Real frozen restart while a paid-call-shaped local request is blocked (no real provider)."""
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
from threading import Event, Lock, Thread
import time
import traceback
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
import yaml

from desktop_verification_support import FrozenDesktop, attach_window
from verification_support import PROJECT_ROOT, eventually
from verify_v07_frozen import RestartedProcess
from v05_acceptance import storage_fingerprint
from v07_mock_server import Handler


class BlockedHandler(Handler):
    def do_POST(self):
        with self.server.started_lock:
            self.server.started += 1
            position = self.server.started
        if position == 1:
            self.server.entered.set()
            if not self.server.release.wait(timeout=110):
                self.send_error(504, 'Synthetic release was not authorized')
                return
        super().do_POST()


def run(bundle):
    evidence = PROJECT_ROOT / '.cache/v07-restart-drain' / uuid4().hex
    evidence.mkdir(parents=True)
    portable = evidence / '中文 空格重启排空目录'
    shutil.copytree(bundle, portable)
    Handler.calls = []
    model = ThreadingHTTPServer(('127.0.0.1', 0), BlockedHandler)
    model.started = 0; model.started_lock = Lock(); model.entered = Event(); model.release = Event()
    thread = Thread(target=model.serve_forever, daemon=True); thread.start()
    config = portable / 'config/ai-providers.yml'; config.parent.mkdir(exist_ok=True)
    config.write_text(yaml.safe_dump({'schema_version': 1, 'default_profile': 'local', 'profiles': {'local': {
        'label': '隔离阻塞模型', 'enabled': True, 'protocol': 'openai_chat',
        'base_url': f'http://127.0.0.1:{model.server_port}', 'model': 'fixture-v07-blocked', 'auth': 'none',
        'response_format': 'json_object', 'max_output_tokens': 4096, 'timeout_seconds': 90}}}, allow_unicode=True), encoding='utf-8')
    (portable / '.env').write_text('MEMORY_OS_AI_ENABLED=true\nMEMORY_OS_RAG_ENABLED=false\nMEMORY_OS_AI_CONFIG_FILE=config/ai-providers.yml\n', encoding='utf-8')
    before = storage_fingerprint(); app = FrozenDesktop(portable, evidence)
    browser = None; page = None; errors = []
    report = {'mode': 'real frozen EXE/WebView2/SQLite + blocked local deterministic HTTP model',
              'bundle': str(bundle), 'real_paid_calls': 0}
    try:
        app.start(); original_pid = app.process.pid
        sources = [app.request('POST', '/api/v1/sources', {'title': f'v07 合成来源 {number}',
            'source_type': 'manual', 'content': f'合成来源第 {number} 篇。仅用于验证重启排空，不含真实用户资料。'}) for number in (1, 2)]
        with sync_playwright() as playwright:
            browser, page = attach_window(playwright, app)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(app.url + '/#/processing')
            for source in sources:
                page.locator(f'input[data-source-id="{source["id"]}"]').check()
            page.get_by_test_id('processing-generate').click()
            expect(page.get_by_role('dialog')).to_contain_text('预计最多 2 次模型调用')
            page.get_by_role('dialog').get_by_role('button', name='开始生成', exact=True).click()
            expect(page.get_by_test_id('processing-batch-detail')).to_be_visible()
            batch_id = page.url.split('batch_id=')[1]
            eventually(model.entered.is_set, timeout=20)
            batch = app.request('GET', '/api/v1/processing/batches/' + batch_id)
            assert batch['counts']['running'] == 1 and batch['counts']['pending'] == 1, batch
            first_run_id = batch['items'][0]['run_id']
            assert model.started == 1 and Handler.calls == []
            page.goto(app.url + '/#/settings')
            page.get_by_test_id('ai-enabled').uncheck()
            page.get_by_test_id('ai-settings-save').click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('dialog').get_by_role('button', name='现在重启', exact=True).click()
            runtime = portable / '.cache/desktop/runtime.json'
            def stopping():
                value = json.loads(runtime.read_text('utf-8'))
                return value if value.get('pid') == original_pid and value.get('status') == 'stopping' else None
            state = eventually(stopping, timeout=40)
            assert app.process.poll() is None
            assert list(runtime.parent.glob('restart-*.ready')), 'Successor must be prepared before drain begins'
            # Pump the real WebView while deliberately keeping the first model call blocked.
            page.wait_for_timeout(1500)
            assert app.process.poll() is None, 'An in-flight response must not be force-terminated'
            assert model.started == 1 and Handler.calls == [], 'No second call may start during drain'
            report['blocked_state'] = {'original_alive': True, 'runtime_status': state['status'],
                                       'started_calls': model.started, 'completed_calls': len(Handler.calls),
                                       'successor_prepared': True}
            model.release.set()
            old_url = app.url; old_process = app.process
            assert old_process.wait(timeout=60) == 0
            def restarted():
                value = json.loads(runtime.read_text('utf-8'))
                return value if value.get('pid') != original_pid and value.get('status') == 'running' else None
            fresh = eventually(restarted, timeout=100)
            app.runtime = fresh; app.url = fresh['url'].rstrip('/'); app.process = RestartedProcess(fresh['pid'])
            assert app._port_closed(old_url)
            try: browser.close()
            except Exception: pass
            browser, page = attach_window(playwright, app)
            page.on('pageerror', lambda error: errors.append(str(error)))
            assert app.request('GET', '/api/v1/ai/profiles')['enabled'] is False
            resumed = app.request('GET', '/api/v1/processing/batches/' + batch_id)
            run = app.request('GET', '/api/v1/processing/runs/' + first_run_id)
            assert resumed['status'] == 'paused', resumed
            assert resumed['counts']['ready'] == 1 and resumed['counts']['pending'] == 1, resumed
            assert resumed['items'][0]['run_id'] == first_run_id and resumed['items'][0]['attempts'] == 1
            assert resumed['items'][1]['run_id'] is None and resumed['items'][1]['attempts'] == 0
            assert run['status'] == 'ready' and run['result']['body'], run
            assert app.request('GET', '/api/v1/knowledge')['total'] == 0
            page.wait_for_timeout(2000)
            assert model.started == 1 and len(Handler.calls) == 1, 'Restart must not reissue a paid request'
            duplicate = subprocess.Popen([str(portable / 'PersonalAiMemoryOs.exe')], cwd=evidence,
                env=app.environment, creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.wait(timeout=20) == 0 and app.process.poll() is None
            assert json.loads(runtime.read_text('utf-8'))['pid'] == fresh['pid']
            page.goto(app.url + '/#/processing?batch_id=' + batch_id)
            expect(page.get_by_test_id('batch-continue')).to_be_enabled()
            page.screenshot(path=str(evidence / 'paused-batch-after-restart.png'), full_page=True)
            assert not errors, errors
            app.request_close(); app.wait_closed(timeout=60)
            report.update(status='passed', initial_pid=original_pid, restarted_pid=fresh['pid'],
                          batch_id=batch_id, ready_run_id=first_run_id, batch_status=resumed['status'],
                          counts=resumed['counts'], started_calls=model.started, completed_calls=len(Handler.calls),
                          mock_calls=Handler.calls, page_errors=errors,
                          checks=['blocked first response survives restart intent', 'successor prepared before draining',
                                  'no second call starts during drain', 'first response persisted as ready',
                                  'same-directory restart uses new PID and saved AI-off configuration',
                                  'remaining item stays pending in paused batch', 'no automatic retry after restart',
                                  'draft remains unadopted with zero Knowledge', 'single instance after restart',
                                  'old and final backend ports released'])
    except Exception as error:
        report.update(status='failed', error=str(error), page_errors=errors)
        (evidence / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        if page:
            try: page.screenshot(path=str(evidence / 'failure.png'), full_page=True)
            except Exception: pass
    finally:
        model.release.set()
        if browser:
            try: browser.close()
            except Exception: pass
        runtime = portable / '.cache/desktop/runtime.json'
        if app.process and app.process.poll() is not None and runtime.exists():
            value = json.loads(runtime.read_text('utf-8'))
            if value.get('status') == 'running' and value.get('pid') != app.process.pid:
                app.process = RestartedProcess(value['pid']); app.url = value['url'].rstrip('/')
        app.stop(); model.shutdown(); model.server_close(); thread.join(timeout=3)
        report['formal_storage_unchanged'] = before == storage_fingerprint()
        if not report['formal_storage_unchanged']: report['status'] = 'failed'
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.bundle.resolve()))
