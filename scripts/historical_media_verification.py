"""Historical-media acceptance orchestration; all exports stay in fresh cache targets."""

import json
from pathlib import Path
import subprocess
import sys
import traceback
from uuid import uuid4

from app.desktop.instance import SingleInstance
from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.browser import ZhihuBrowser
from app.services.zhihu_sync.configuration import Configuration, SyncConfiguration
from app.services.zhihu_sync.runner import run_collection
from app.services.zhihu_sync.storage import identity_key, safe_path
from scripts.historical_media_inventory import audit_inventory, files_snapshot, protected_snapshot, select_cases
from scripts.historical_media_execution import CaptureBrowser, NoNetworkBrowser, recover_interrupted, verify_exports

ROOT = Path(__file__).resolve().parents[1]


def cache_run(path):
    # Check reparse entries before resolving, including junctions into a formal
    # directory within this workspace. A prefix check alone would accept them.
    cache = safe_path(ROOT / '.cache/zhihu-media')
    path = safe_path(Path(path))
    if not cache.is_relative_to(ROOT.resolve()) or path == cache or not path.is_relative_to(cache):
        raise ValueError('verification_path_escape')
    return path


def save(path, value):
    safe_path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def reopen_worker(output):
    output = cache_run(output)
    manifest = json.loads(safe_path(output / 'reopen-input.json').read_text(encoding='utf-8'))
    config = SyncConfiguration.model_validate(manifest['config'])
    if Path(config.target_dir).resolve() != output / 'articles':
        raise ValueError('reopen_target_escape')
    identities = [normalize_zhihu_url(url) for url in manifest['urls']]
    before = files_snapshot(Path(config.target_dir), timestamps=True)
    assert before == manifest['published_snapshot'], 'Published files changed before reopen'
    report = run_collection(config, NoNetworkBrowser(identities), lambda: False, lambda value: None)
    assert report['created'] == report['failed'] == 0 and report['skipped'] == len(identities)
    assert before == files_snapshot(Path(config.target_dir), timestamps=True)
    save(output / 'reopen-report.json', {'status': 'passed', 'network_requests': 0, 'report': report})
    return 0


def check_reopen(output, config, identities):
    save(output / 'reopen-input.json', {'config': config.model_dump(), 'urls': [i.canonical_url for i in identities],
                                      'published_snapshot': files_snapshot(Path(config.target_dir), timestamps=True)})
    with (output / 'reopen.log').open('w', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ROOT / 'scripts/verify_zhihu_media.py'),
            '--reopen-worker', str(output)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            timeout=120, check=False)
    if result.returncode:
        raise RuntimeError('independent_reopen_failed')
    return json.loads((output / 'reopen-report.json').read_text(encoding='utf-8'))


def save_capture(output, captured):
    folder = output / 'responses'
    folder.mkdir()
    import hashlib
    images = {}
    for url, data in captured.images.items():
        name = hashlib.sha256(data).hexdigest() + '.bin'
        (folder / name).write_bytes(data)
        images[url] = name
    save(folder / 'manifest.json', {'articles': captured.articles, 'images': images})


def execute_suite(runtime, original, config, output, report):
    with ZhihuBrowser(runtime) as browser:
        online = browser.collection(config.collection_url)
        identities = {identity_key(i): i for i in online}
        entries, inventory = audit_inventory(original)
        report['inventory'] = inventory
        if inventory['errors']:
            raise RuntimeError('historical_image_health_failed')
        selected, coverage = select_cases(entries, set(identities))
        selected_ids = [identities[e['identity']] for e in selected]
        report.update(coverage=coverage, collection_visible=len(online), site_unlisted=browser.unlisted_count,
            historical_not_in_current_collection=sum(e['identity'] not in identities for e in entries))
        target = output / 'articles'
        target.mkdir()
        isolated = config.model_copy(update={'target_dir': str(target), 'enabled': False})
        captured = CaptureBrowser(browser, selected_ids)
        report['first'] = run_collection(isolated, captured, lambda: False, lambda value: None)
        save_capture(output, captured)
        if report['first']['created'] != len(selected_ids) or report['first']['failed']:
            raise RuntimeError('historical_export_incomplete')
        report['export_verification'] = verify_exports(target, captured, selected_ids, coverage)
        before = files_snapshot(target, timestamps=True)
        requests = (captured.article_calls, captured.image_calls)
        report['repeat'] = run_collection(isolated, captured, lambda: False, lambda value: None)
        assert report['repeat']['created'] == report['repeat']['failed'] == 0
        assert report['repeat']['skipped'] == len(selected_ids)
        assert requests == (captured.article_calls, captured.image_calls)
        assert before == files_snapshot(target, timestamps=True)
        report['reopen'] = check_reopen(output, isolated, selected_ids)
        assert before == files_snapshot(target, timestamps=True)
        multi = next(identities[c['identity']] for c in coverage if c['case'] == 'answer.multiple')
        report['recovery'] = recover_interrupted(isolated, captured, multi, output)
        report.update(selected_count=len(selected_ids), body_requests=captured.article_calls,
                      image_requests=captured.image_calls, repeat_additional_body_and_image_requests=0)


def run_historical(runtime, *, execute=False):
    runtime = Path(runtime).resolve()
    output = cache_run(ROOT / '.cache/zhihu-media' / uuid4().hex)
    output.mkdir(parents=True)
    report = {'status': 'failed', 'suite': 'historical-images', 'model_calls': 0,
        'newly_favorited_content': False, 'scope': 'Historical favorites exported for the first time into a fresh isolated target.'}
    lease = before = None
    try:
        config = Configuration(runtime).load()
        original = Path(config.target_dir)
        if execute:
            lease = SingleInstance(runtime)
            if not lease.owner:
                raise RuntimeError('desktop_must_be_normally_closed')
            before = protected_snapshot(runtime, original)
            save(output / 'protected-before.json', before)
            execute_suite(runtime, original, config, output, report)
            report['status'] = 'passed'
        else:
            initial = files_snapshot(original)
            entries, inventory = audit_inventory(original)
            report['inventory'] = inventory
            if inventory['errors']:
                raise RuntimeError('historical_image_health_failed')
            selected, coverage = select_cases(entries)
            assert initial == files_snapshot(original), 'Historical input changed during preview'
            report.update(status='previewed', selected_count=len(selected), coverage=coverage, network_requests=0)
    except Exception as error:
        report['error'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        safe_path(output / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if before is not None:
            try:
                after = protected_snapshot(runtime, original)
                save(output / 'protected-after.json', after)
                report['formal_data_unchanged'] = before == after
                if before != after:
                    report.update(status='failed', error='formal_data_changed')
            except Exception as error:
                report.update(status='failed', integrity_error=type(error).__name__)
        if lease is not None:
            lease.close()
        save(output / 'report.json', report)
    print(json.dumps({'status': report['status'], 'report': str(output / 'report.json'),
                      'selected_count': report.get('selected_count'), 'model_calls': 0}, ensure_ascii=False), flush=True)
    return 0 if report['status'] in {'passed', 'previewed'} else 1
