"""Prepare a cache-only input fixture; verify externally observed native Save As UI."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.desktop.update_resources import digest, read_manifest
from scripts.build_desktop import inspect_bundle

CACHE = ROOT / '.cache/native-save-as'
SAVED_NAME = '原生保存报告.json'
CANCELLED_NAME = '取消不应创建.json'


def business_snapshot():
    database = ROOT / 'dist/PersonalAiMemoryOs-0.6.6/data/memory.db'
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        return {name: hashlib.sha256(json.dumps(sorted(connection.execute('SELECT * FROM ' + name).fetchall(), key=str),
                ensure_ascii=False, default=str).encode()).hexdigest()
                for name in ('sources', 'knowledge', 'organization_calls', 'topic_summaries')}


def evidence_directory(value):
    value = value.resolve()
    if (not CACHE.resolve().is_relative_to(ROOT.resolve()) or value == CACHE.resolve()
            or not value.is_relative_to(CACHE.resolve())):
        raise ValueError('Evidence must be a child of the project .cache/native-save-as directory')
    return value


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def load_context(directory):
    directory = evidence_directory(directory)
    value = json.loads((directory / 'context.json').read_text(encoding='utf-8'))
    if Path(value['runtime']).resolve() != directory / 'portable':
        raise ValueError('Unexpected isolated runtime path')
    return directory, value, directory / 'portable'


def export_hashes(runtime):
    exports = runtime / 'exports'
    result = {}
    for path in exports.rglob('*'):
        if path.is_file():
            if not path.resolve().is_relative_to(exports.resolve()):
                raise ValueError('Export file escapes its isolated directory')
            result[path.relative_to(exports).as_posix()] = digest(path)
    return result


def prepare(bundle, launch=False):
    bundle = bundle.resolve()
    if not bundle.is_relative_to((ROOT / '.cache').resolve()):
        raise ValueError('Use a pristine bundle under the project .cache directory')
    inspect_bundle(bundle)
    manifest = read_manifest(bundle)
    output = evidence_directory(CACHE / uuid4().hex)
    output.mkdir(parents=True)
    runtime = output / 'portable'
    shutil.copytree(bundle, runtime)
    assets = runtime / '_internal/app/web'
    fixture = assets / 'js/native-save-fixture.js'
    if fixture.exists():
        raise ValueError('The input bundle already contains a test fixture')
    shutil.copyfile(ROOT / 'scripts/fixtures/native-save-fixture.js', fixture)
    index = assets / 'index.html'
    index.write_text(index.read_text(encoding='utf-8').replace('</body>',
        '<script type="module" src="/assets/js/native-save-fixture.js"></script>\n</body>'), encoding='utf-8')
    (runtime / '.env').write_text('MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=false\n'
        'MEMORY_OS_SYNC_ENABLED=false\nMEMORY_OS_DATABASE_URL=sqlite:///data/memory.db\n'
        'MEMORY_OS_KNOWLEDGE_DIR=knowledge\n', encoding='utf-8')
    state = {'runtime': str(runtime), 'bundle': str(bundle), 'version': manifest['version'],
        'formal_before': business_snapshot(), 'model_calls': 0,
        'modified_test_assets': {'_internal/app/web/index.html': digest(index),
                                '_internal/app/web/js/native-save-fixture.js': digest(fixture)}}
    if launch:
        environment = {k: v for k, v in os.environ.items() if not k.startswith(('MEMORY_OS_', 'PYTHON', 'WEBVIEW2_', 'UV_'))}
        environment.update(MEMORY_OS_AI_ENABLED='false', MEMORY_OS_RAG_ENABLED='false', MEMORY_OS_SYNC_ENABLED='false')
        with (output / 'launch.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(runtime / 'PersonalAiMemoryOs.exe')], cwd=runtime, env=environment,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        state['pid'] = process.pid
    save_json(output / 'context.json', state)
    return {'status': 'prepared', 'evidence': str(output), 'runtime': str(runtime), 'model_calls': 0}


def checkpoint(directory):
    directory, state, runtime = load_context(directory)
    raw = (runtime / 'exports' / SAVED_NAME).read_bytes()
    value = json.loads(raw.decode('utf-8'))
    assert value['dry_run'] and value['total'] == value['would_create'] == 1 and value['created'] == 0
    assert value['items'][0]['status'] == 'would_create'
    assert all('content' not in item for item in value['items'])
    result = {'utf8_json': True, 'dry_run': True, 'total': 1, 'would_create': 1, 'created': 0,
              'saved_name': SAVED_NAME, 'bytes': len(raw), 'exports_before_cancel': export_hashes(runtime)}
    assert set(result['exports_before_cancel']) == {SAVED_NAME}
    save_json(directory / 'save-check.json', result)
    return {'status': 'save_checked', 'bytes': len(raw)}


def verify(directory, native_ui_confirmed):
    directory, state, runtime = load_context(directory)
    saved = json.loads((directory / 'save-check.json').read_text(encoding='utf-8'))
    assert export_hashes(runtime) == saved['exports_before_cancel']
    assert not (runtime / 'exports' / CANCELLED_NAME).exists()
    manifest = read_manifest(Path(state['bundle']))
    assert set(state['modified_test_assets']) == {'_internal/app/web/index.html', '_internal/app/web/js/native-save-fixture.js'}
    for item in manifest['files']:
        expected = state['modified_test_assets'].get(item['path'], item['sha256'])
        assert digest(runtime / item['path']) == expected
    for relative, expected in state['modified_test_assets'].items():
        assert digest(runtime / relative) == expected
    assert business_snapshot() == state['formal_before']
    with sqlite3.connect((runtime / 'data/memory.db').resolve().as_uri() + '?mode=ro', uri=True) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('SELECT count(*) FROM sources').fetchone()[0] == 0
    result = {'status': 'passed' if native_ui_confirmed else 'ui_confirmation_pending', 'version': state['version'],
        'native_ui_operator_confirmed': native_ui_confirmed, 'saved_utf8_json_bytes': saved['bytes'],
        'cancel_creates_no_export': True, 'saved_report_unchanged': True, 'formal_business_rows_unchanged': True,
        'production_exe_and_handlers_unchanged': True, 'model_calls': 0,
        'scope': 'Normal EXE and original import/report/native download code; cloned index and added JS load synthetic input. Native input picker is outside this acceptance.'}
    save_json(directory / 'verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    setup = actions.add_parser('prepare')
    setup.add_argument('--bundle', type=Path, required=True)
    setup.add_argument('--launch', action='store_true')
    for name in ('checkpoint-save', 'verify'):
        command = actions.add_parser(name)
        command.add_argument('--evidence', type=Path, required=True)
        if name == 'verify':
            command.add_argument('--confirm-native-ui', action='store_true',
                help='Attest that an operator observed native Save As save and cancel; filesystem checks alone cannot prove UI actions')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Windows is required')
    if args.action == 'prepare':
        result = prepare(args.bundle, args.launch)
    elif args.action == 'checkpoint-save':
        result = checkpoint(args.evidence)
    else:
        result = verify(args.evidence, args.confirm_native_ui)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['status'] == 'ui_confirmation_pending' else 0


if __name__ == '__main__':
    raise SystemExit(main())
