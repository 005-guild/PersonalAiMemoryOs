"""Frozen collection settings/scan/reopen smoke test; never calls a real model."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import traceback
from uuid import uuid4
from playwright.sync_api import expect,sync_playwright
from desktop_verification_support import FrozenDesktop,attach_window
from verification_support import PROJECT_ROOT
from v06_acceptance import browser_environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args()
    evidence=PROJECT_ROOT/'.cache/collection-desktop'/uuid4().hex;evidence.mkdir(parents=True)
    root=evidence/'portable';shutil.copytree(args.bundle,root)
    source=evidence/'articles';source.mkdir()
    for number in range(1,4):
        (source/f'{number}.md').write_text(f'---\ntitle: 合成资料{number}\nsource: https://zhuanlan.zhihu.com/p/{number}\n---\n完整的合成原文。',encoding='utf-8')
    app=FrozenDesktop(root,evidence)
    report={'status':'failed','real_model_calls':0}
    try:
        with browser_environment(evidence/'driver'),sync_playwright() as p:
            app.start();browser,page=attach_window(p,app)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(app.url+'/#/organization')
            page.get_by_label('原文目录',exact=True).fill(str(source))
            page.get_by_label('整理库目录',exact=True).fill(str(evidence/'organized'))
            page.get_by_role('button',name='保存设置',exact=True).click()
            expect(page.get_by_text('操作已保存，进度会自动刷新。',exact=True)).to_be_visible()
            page.get_by_role('button',name='扫描原文',exact=True).click()
            expect(page.get_by_text('发现 3 篇；长文 0 篇；需识图 0 篇。',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='开始全量整理',exact=True)).to_be_disabled()
            page.screenshot(path=str(evidence/'collection-settings.png'),full_page=True)
            app.request_close();app.wait_closed();app.start();browser,page=attach_window(p,app)
            page.goto(app.url+'/#/organization')
            expect(page.get_by_label('原文目录',exact=True)).to_have_value(str(source))
            expect(page.get_by_text('待整理 3',exact=True)).to_be_visible()
            assert not errors,errors
            app.request_close();app.wait_closed()
        with sqlite3.connect(root/'data/memory.db') as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0008'
            assert db.execute('SELECT count(*) FROM organization_calls').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM organization_items').fetchone()[0]==3
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        report.update(status='passed',checks=['settings','scan','approval_gate','reopen','zero_model_calls','sqlite_integrity'])
    except Exception:
        (evidence/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        app.stop();(evidence/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(evidence/'report.json')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':sys.exit(main())
