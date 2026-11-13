"""Check the frozen settings UI and bundled Chromium in an isolated installation."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from desktop_verification_support import FrozenDesktop, attach_window
from verification_support import PROJECT_ROOT, eventually
from v06_acceptance import browser_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--check-login-wall', action='store_true',
                        help='Read the public Zhihu collection anonymously to verify bundled Chromium.')
    parser.add_argument('--collection', help='Explicit collection URL for the optional anonymous check.')
    args = parser.parse_args()
    if args.check_login_wall and not args.collection:
        parser.error('--check-login-wall requires an explicit --collection URL')
    evidence = PROJECT_ROOT / '.cache/zhihu-desktop-validation' / uuid4().hex
    evidence.mkdir(parents=True)
    root = evidence / 'portable'
    shutil.copytree(args.bundle, root)
    app = FrozenDesktop(root, evidence)
    report = {'status':'failed', 'authenticated_sync_tested':False}
    try:
        with browser_environment(evidence / 'driver-tmp'), sync_playwright() as p:
            app.start()
            browser, page = attach_window(p, app)
            errors = []
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(app.url + '/#/settings')
            panel = page.get_by_test_id('zhihu-sync-settings')
            expect(panel).to_be_visible()
            expect(panel.get_by_role('button',name='保存同步设置')).to_be_enabled()
            panel.get_by_label('收藏夹链接',exact=True).fill(args.collection or 'https://www.zhihu.com/collection/1')
            panel.get_by_label('保存目录',exact=True).fill(str(evidence / 'export/articles'))
            with page.expect_response(lambda r:r.url.endswith('/zhihu-sync') and r.request.method=='PUT') as response:
                panel.get_by_role('button',name='保存同步设置').click()
            assert response.value.status == 200
            assert not response.value.json()['enabled']
            panel.scroll_into_view_if_needed()
            page.screenshot(path=str(evidence / 'zhihu-settings.png'))
            if args.check_login_wall:
                panel.get_by_role('button',name='预演',exact=True).click()
                def finished():
                    value=app.request('GET','/api/v1/settings/zhihu-sync')
                    return value if value['status']['state']=='failed' else None
                result=eventually(finished,timeout=90)
                assert result['status']['last_error']=='login_required', result['status']
                assert result['paused']
                assert not (evidence / 'export').exists()
                report['packaged_browser_login_wall']='passed'
            assert not errors, errors
            report.update(status='passed',settings_saved=True,automatic_sync_disabled=True)
            app.request_close()
            app.wait_closed()
    except Exception:
        (evidence / 'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        app.stop()
        (evidence / 'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence / 'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__ == '__main__':
    sys.exit(main())
