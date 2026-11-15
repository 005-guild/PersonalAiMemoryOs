"""Historical acceptance selection, actual image fidelity and disk-backed recovery."""

from io import BytesIO
import json
from pathlib import Path
import stat
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image
import pytest

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.configuration import SyncConfiguration
from app.services.zhihu_sync.export import render
from app.services.zhihu_sync.runner import run_collection
from scripts.historical_media_inventory import audit_inventory, files_snapshot, protected_snapshot, select_cases
from scripts.historical_media_execution import CaptureBrowser, recover_interrupted, verify_exports
from scripts import historical_media_verification as suite


def image_bytes(color='red', size=(3, 2)):
    stream = BytesIO()
    with Image.new('RGB', size, color) as image:
        image.save(stream, format='PNG')
    return stream.getvalue()


def identity(kind='answer', number='123'):
    return normalize_zhihu_url({'answer': f'https://www.zhihu.com/question/1/answer/{number}',
        'article': f'https://zhuanlan.zhihu.com/p/{number}', 'pin': f'https://www.zhihu.com/pin/{number}'}[kind])


def entry(kind, number, count, *, long=False, visual=False):
    return {'identity': kind + ':' + number, 'resource_type': kind, 'external_id': number,
            'images': [{}] * count, 'distinct_images': count, 'long_image': long, 'image_centric': visual}


def test_selection_has_six_core_cases_plus_nonoverlapping_long_and_visual_cases():
    values = [entry(kind, number, count) for kind in ('answer', 'article', 'pin')
              for number, count in [('10', 1), ('20', 2)]]
    values += [entry('answer', '30', 1, long=True), entry('answer', '40', 1, visual=True), entry('pin', '2', 1)]
    selected, coverage = select_cases(values)
    assert len(selected) == len(coverage) == 8
    assert next(c for c in coverage if c['case'] == 'pin.single')['identity'] == 'pin:2'
    assert {c['case'] for c in coverage} >= {'long_image', 'image_centric', 'article.multiple'}


def test_selection_reuses_existing_coverage_and_requires_online_candidates():
    values = [entry(kind, number, count, long=kind == 'answer', visual=kind == 'answer')
              for kind in ('answer', 'article', 'pin') for number, count in [('1', 1), ('2', 2)]]
    assert len(select_cases(values)[0]) == 6
    available = {e['identity'] for e in values} - {'article:2'}
    with pytest.raises(RuntimeError, match='coverage_missing:article.multiple'):
        select_cases(values, available)


def test_inventory_decodes_long_images_and_preserves_unreferenced_files(tmp_path):
    root = tmp_path / 'articles'; (root / 'images').mkdir(parents=True)
    (root / 'images/long.png').write_bytes(image_bytes(size=(1, 8193)))
    (root / 'images/unreferenced.png').write_bytes(image_bytes('blue'))
    payload = render(identity(), 'Synthetic', None, '<p>short</p>', '2026-11-15')
    (root / 'test.md').write_text(payload['content'] + '\n![](images/long.png)\n', encoding='utf-8')
    before = files_snapshot(root, timestamps=True)
    entries, summary = audit_inventory(root)
    assert not summary['errors'] and summary['physical_image_files'] == summary['healthy_images'] == 2
    assert summary['unreferenced_files'] == ['images/unreferenced.png']
    assert entries[0]['long_image'] and entries[0]['image_centric']
    assert files_snapshot(root, timestamps=True) == before


def test_inventory_reports_corrupt_files_and_escaping_references(tmp_path):
    root = tmp_path / 'articles'; (root / 'images').mkdir(parents=True)
    (root / 'images/bad.png').write_bytes(b'not an image')
    payload = render(identity(), 'Synthetic', None, '<p>short</p>', '2026-11-15')
    (root / 'test.md').write_text(payload['content'] + '\n![](images/bad.png)\n![](../outside.png)', encoding='utf-8')
    _, summary = audit_inventory(root)
    assert summary['physical_image_files'] == 1 and summary['healthy_images'] == 0
    assert {e['code'] for e in summary['errors']} >= {'image_missing', 'UnidentifiedImageError'}


def test_inventory_decodes_all_animation_frames_without_reencoding(tmp_path):
    root = tmp_path / 'articles'; (root / 'images').mkdir(parents=True)
    path = root / 'images/animated.gif'
    with Image.new('RGB', (3, 2), 'red') as first, Image.new('RGB', (3, 2), 'blue') as second:
        first.save(path, save_all=True, append_images=[second], duration=100, loop=0)
    before = path.read_bytes()
    _, report = audit_inventory(root)
    assert report['animated_files'] == 1 and report['decoded_frames'] == 2 and not report['errors']
    assert path.read_bytes() == before


@pytest.mark.parametrize('area', ['originals', 'completion_ledger', 'organized_mirror', 'vault', 'configuration', 'database_and_environment'])
def test_protected_fingerprints_detect_formal_changes_without_secret_values(tmp_path, area):
    runtime = tmp_path / 'runtime'; original = tmp_path / 'favorites/articles'
    paths = {'originals': original / 'note.md', 'completion_ledger': original.parent / '.sync/state.json',
        'organized_mirror': original.parent / '整理库/note.md', 'vault': runtime / 'knowledge/note.md',
        'configuration': runtime / 'config/private.yml', 'database_and_environment': runtime / 'data/memory.db'}
    path = paths[area]; path.parent.mkdir(parents=True); path.write_text('SYNTHETIC_SECRET', encoding='utf-8')
    before = protected_snapshot(runtime, original)
    assert 'SYNTHETIC_SECRET' not in json.dumps(before)
    path.write_text('changed', encoding='utf-8')
    assert before != protected_snapshot(runtime, original)


class Source:
    def __init__(self, *, duplicate=False):
        self.images = {'https://picx.zhimg.com/a.png': image_bytes(), 'https://picx.zhimg.com/b.png': image_bytes('blue')}
        self.html = '<p>short</p><img data-original="https://picx.zhimg.com/a.png"><img src="https://picx.zhimg.com/b.png">'
        if duplicate:
            self.html += '<img src="https://picx.zhimg.com/a.png"><img data-tex="x^2" src="https://www.zhihu.com/equation?x">'

    def article(self, value):
        return {'title': 'Synthetic', 'author': None, 'html': self.html}

    def image(self, url):
        return self.images[url]


def exported(target, *, duplicate=False):
    target.mkdir(parents=True)
    config = SyncConfiguration(collection_url='https://www.zhihu.com/collection/123', target_dir=str(target.resolve()))
    captured = CaptureBrowser(Source(duplicate=duplicate), [identity()])
    report = run_collection(config, captured, lambda: False, lambda value: None)
    assert report['created'] == 1 and report['failed'] == 0
    return config, captured


def test_export_verifier_checks_duplicate_references_order_and_bytes(tmp_path):
    config, captured = exported(tmp_path / 'articles', duplicate=True)
    result = verify_exports(Path(config.target_dir), captured, [identity()])
    assert result['references_verified'] == 3 and result['images_verified'] == 2
    path = next((Path(config.target_dir) / 'images').glob('*'))
    path.write_bytes(image_bytes('green'))
    with pytest.raises(AssertionError, match='Image bytes or order changed'):
        verify_exports(Path(config.target_dir), captured, [identity()])


@pytest.mark.parametrize('damage', ['missing_reference', 'reversed_order'])
def test_export_verifier_rejects_missing_or_reordered_images(tmp_path, damage):
    config, captured = exported(tmp_path / 'articles')
    target = Path(config.target_dir)
    path = next(target.glob('*.md'))
    text = path.read_text(encoding='utf-8')
    from app.services.organization.inventory import inspect_directory
    references = [i['reference'] for i in inspect_directory(target)[0]['images']]
    if damage == 'missing_reference':
        text = text.replace('![](' + references[0] + ')', '')
    else:
        text = text.replace(references[0], 'temporary-reference').replace(references[1], references[0]).replace('temporary-reference', references[1])
    path.write_text(text, encoding='utf-8')
    with pytest.raises(AssertionError):
        verify_exports(target, captured, [identity()])


def test_recovery_uses_captured_real_bytes_and_no_completed_image_refetch(tmp_path):
    config, captured = exported(tmp_path / 'articles')
    result = recover_interrupted(config, captured, identity(), tmp_path / 'evidence')
    assert result['failure']['failed'] == 1 and result['resume']['created'] == 1
    assert result['resume_body_requests'] == 0 and result['retained_image_refetched'] is False


def test_independent_worker_reloads_completion_without_network():
    output = suite.cache_run(suite.ROOT / '.cache/zhihu-media' / ('unit-' + uuid4().hex))
    output.mkdir(parents=True)
    config, _ = exported(output / 'articles')
    result = suite.check_reopen(output, config, [identity()])
    assert result['network_requests'] == 0 and result['report']['skipped'] == 1


def test_reopen_worker_refuses_context_pointing_outside_its_run(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    output = suite.cache_run(tmp_path / '.cache/zhihu-media/run'); output.mkdir(parents=True)
    config = SyncConfiguration(collection_url='https://www.zhihu.com/collection/123', target_dir=str(tmp_path / 'formal'))
    (output / 'reopen-input.json').write_text(json.dumps({'config': config.model_dump(), 'urls': []}), encoding='utf-8')
    with pytest.raises(ValueError, match='reopen_target_escape'):
        suite.reopen_worker(output)
    assert not (tmp_path / 'formal').exists()


def test_reopen_worker_rejects_changed_published_files_before_running(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    output = suite.cache_run(tmp_path / '.cache/zhihu-media/run'); output.mkdir(parents=True)
    config, _ = exported(output / 'articles')
    snapshot = files_snapshot(output / 'articles', timestamps=True)
    suite.save(output / 'reopen-input.json', {'config': config.model_dump(), 'urls': [identity().canonical_url], 'published_snapshot': snapshot})
    next((output / 'articles').glob('*.md')).write_text('changed', encoding='utf-8')
    with pytest.raises(AssertionError, match='Published files changed before reopen'):
        suite.reopen_worker(output)


def test_historical_preview_does_not_construct_browser_or_take_desktop_lease(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    runtime = tmp_path / 'runtime'; (runtime / 'config').mkdir(parents=True)
    config = SyncConfiguration(collection_url='https://www.zhihu.com/collection/123', target_dir=str(tmp_path / 'articles'))
    (runtime / 'config/zhihu-sync.yml').write_text(json.dumps(config.model_dump()), encoding='utf-8')
    values = [entry(kind, number, count, long=kind == 'answer', visual=kind == 'answer')
              for kind in ('answer', 'article', 'pin') for number, count in [('1', 1), ('2', 2)]]
    monkeypatch.setattr(suite, 'audit_inventory', lambda root: (values, {'errors': []}))
    def forbidden(*args, **kwargs):
        raise AssertionError('Preview touched authenticated runtime')
    monkeypatch.setattr(suite, 'ZhihuBrowser', forbidden)
    monkeypatch.setattr(suite, 'SingleInstance', forbidden)
    assert suite.run_historical(runtime) == 0
    report = json.loads(next((tmp_path / '.cache/zhihu-media').glob('*/report.json')).read_text(encoding='utf-8'))
    assert report['status'] == 'previewed' and report['network_requests'] == 0


@pytest.mark.parametrize('destination', ['cache_root', 'report_file'])
def test_windows_reparse_entries_are_rejected_before_read_or_write(tmp_path, monkeypatch, destination):
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    cache = tmp_path / '.cache/zhihu-media'
    blocked = cache if destination == 'cache_root' else cache / 'run/report.json'
    original_lstat = Path.lstat
    def redirected(path, *args, **kwargs):
        if path == blocked:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original_lstat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', redirected)
    with pytest.raises(ValueError):
        if destination == 'cache_root':
            suite.cache_run(cache / 'run')
        else:
            suite.save(blocked, {'value': 'must not write'})
    assert not blocked.exists()
