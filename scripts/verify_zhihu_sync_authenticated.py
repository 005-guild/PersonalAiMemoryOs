"""Verify an explicitly selected running desktop against its logged-in collection.

The default only previews. --sync writes new exports and repeats the operation
to check deduplication. Evidence stays private under .cache; tokens are not saved.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.import_types import ParsedZhihuItem
from app.services.zhihu_markdown import _entry


def fingerprint(target):
    return {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in target.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--sync', action='store_true', help='Export new files, then verify a repeat creates zero files.')
    args = parser.parse_args()
    runtime = json.loads((args.runtime / '.cache/desktop/runtime.json').read_text(encoding='utf-8'))
    base = runtime['url'].rstrip('/')
    address = urlsplit(base)
    if address.scheme != 'http' or address.hostname != '127.0.0.1' or address.username or address.path:
        parser.error('Expected the selected desktop loopback URL')
    evidence = ROOT / '.cache/zhihu-authenticated-validation' / uuid4().hex
    evidence.mkdir(parents=True)
    opener = build_opener(ProxyHandler({}))
    endpoint = '/api/v1/settings/zhihu-sync'

    def request(method='GET', suffix='', token=None):
        headers = {'Content-Type': 'application/json', 'Origin': base}
        if token:
            headers['X-Configuration-Token'] = token
        with opener.open(Request(base + endpoint + suffix, method=method, headers=headers,
                                 data=b'{}' if method == 'POST' else None), timeout=30) as response:
            return json.load(response)

    config = request()
    if config['enabled'] or config['status']['state'] in {'running', 'queued'}:
        parser.error('Disable automatic synchronization and wait for the current operation first')
    target = Path(config['target_dir'])
    if not target.is_absolute() or not target.is_dir():
        parser.error('The selected export directory must already exist')
    before = fingerprint(target)
    (evidence / 'before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'status': 'failed', 'writes_requested': args.sync, 'files_before': len(before)}

    def action(name):
        value = request()
        request('POST', '/' + name, value['csrf_token'])
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            value = request()
            if value['status']['state'] not in {'running', 'queued'}:
                result = value['status']
                print(json.dumps({'action': name, **result}), flush=True)
                assert result['state'] == 'finished', result
                assert result['report']['failed'] == 0, result['report']
                return result['report']
            time.sleep(2)
        raise TimeoutError('The selected synchronization operation did not finish')

    try:
        report['preview'] = action('preview')
        assert fingerprint(target) == before, 'Preview modified exported files'
        if args.sync:
            report['first_run'] = action('run')
            after = fingerprint(target)
            assert all(after.get(name) == digest for name, digest in before.items()), 'Existing file changed'
            new_markdown = [name for name in after.keys() - before.keys() if name.endswith('.md')]
            assert len(new_markdown) == report['first_run']['created']
            seen = set()
            image_references = 0
            for index, name in enumerate(new_markdown):
                content = (target / name).read_text(encoding='utf-8')
                parsed, _ = _entry(index, {'relative_path': name, 'content': content}, seen)
                assert isinstance(parsed, ParsedZhihuItem), 'Export is incompatible with the existing importer'
                for relative in re.findall(r'!\[[^\]]*\]\((images/[^\s)]+)', content):
                    image = (target / relative).resolve()
                    assert image.is_relative_to(target.resolve()) and image.is_file() and image.stat().st_size
                    image_references += 1
            report['repeat'] = action('run')
            assert report['repeat']['created'] == 0 and fingerprint(target) == after, 'Repeat changed exports'
            report.update(existing_files_unchanged=True, new_markdown=len(new_markdown),
                          local_image_references=image_references, files_after=len(after))
        report['status'] = 'passed'
    except Exception as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(evidence / 'report.json'), 'status': report['status']}), flush=True)


if __name__ == '__main__':
    main()
