"""Source or frozen bookshelf acceptance, synthetic data only, zero paid calls."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import traceback
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.desktop.server import DesktopServer
from reading_verification_support import seed, browser_checks
from v06_acceptance import browser_environment
from desktop_verification_support import FrozenDesktop, attach_window
from playwright.sync_api import sync_playwright


def snapshot(root):
    with sqlite3.connect(root / 'data/memory.db') as database:
        return '\n'.join(database.iterdump())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    evidence = ROOT / '.cache/reading-verification' / uuid4().hex; evidence.mkdir(parents=True)
    root = evidence / 'portable'
    if args.bundle: shutil.copytree(args.bundle, root)
    else: root.mkdir()
    for key in list(os.environ):
        if key.startswith('MEMORY_OS_'): del os.environ[key]
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.cache/playwright')
    settings = Settings(_env_file=None, runtime_root=root, database_url='sqlite:///' + (root/'data/memory.db').as_posix(),
                        sync_enabled=False, ai_enabled=False, rag_enabled=False)
    identifier = seed(root, settings)
    (root/'.env').write_text('MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=false\nMEMORY_OS_SYNC_ENABLED=false\n', encoding='utf-8')
    report = {'status': 'failed', 'real_model_calls': 0, 'frozen': bool(args.bundle)}
    server = FrozenDesktop(root, evidence) if args.bundle else DesktopServer(settings)
    try:
        server.start()
        before = snapshot(root)
        with browser_environment(evidence/'driver'), sync_playwright() as playwright:
            if args.bundle: browser, page = attach_window(playwright, server)
            else:
                browser = playwright.chromium.launch(channel='chromium', args=['--no-proxy-server'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1100}, locale='zh-CN')
            checks = browser_checks(page, server.url, identifier, evidence)
            # Reading acceptance closes an idle window; active-request draining
            # is exercised separately by verify_desktop's lifecycle workflow.
            page.wait_for_load_state('networkidle')
            assert snapshot(root) == before, 'Reading changed database records'
            if args.bundle:
                server.request_close(); server.wait_closed(); server.start(); browser, page = attach_window(playwright, server)
                page.goto(server.url + '/#/reading')
                page.get_by_role('heading', name='收藏之后，慢慢读。').wait_for()
                server.request_close(); server.wait_closed(); checks.append('frozen_reopen')
            else: browser.close()
        report.update(status='passed', checks=checks, articles=35)
    except Exception:
        (evidence/'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        try: page.screenshot(path=str(evidence/'failure.png'))
        except Exception: pass
    finally:
        server.stop()
        (evidence/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(evidence/'report.json')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
