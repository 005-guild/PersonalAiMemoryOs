"""Append-only export must survive restarts, deletion, partial images and crashes."""
import json
from pathlib import Path

import pytest

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.storage import Ledger, SyncError, writer_lock
from app.services.zhihu_sync.export import Exporter, render, image_url, publish_file


URL = 'https://www.zhihu.com/question/1/answer/2000991203269820437'


def setup(tmp_path):
    target = tmp_path / 'collection/articles'
    target.mkdir(parents=True)
    identity = normalize_zhihu_url(URL)
    payload = render(identity, '测试 / 标题', '作者', '<p>完整正文</p>', '2026-11-14')
    return target, identity, payload


def test_adopt_existing_then_deleted_file_is_still_complete(tmp_path):
    target, identity, payload = setup(tmp_path)
    original = target / '原文件名.md'
    original.write_text(payload['content'], encoding='utf-8')
    before = original.read_bytes()
    ledger = Ledger(target, '123').load()
    ledger.save()
    assert original.read_bytes() == before
    original.unlink()
    assert 'answer:2000991203269820437' in Ledger(target, '123').load().records


def test_preview_does_not_write(tmp_path):
    target, _, _ = setup(tmp_path)
    Ledger(target, '123').load()
    assert not (target.parent / '.sync').exists()


def test_publication_does_not_alias_staging_and_final_files(tmp_path):
    source, target = tmp_path/'stage', tmp_path/'final'
    source.write_bytes(b'original')
    publish_file(source,target)
    source.write_bytes(b'retry must not overwrite final')
    assert target.read_bytes() == b'original'
    with pytest.raises(SyncError,match='output_conflict'):
        publish_file(source,target)


def test_registered_local_edits_are_not_reparsed_or_overwritten(tmp_path):
    target, _, payload = setup(tmp_path)
    path=target/'local.md'
    path.write_text(payload['content'],encoding='utf-8')
    ledger=Ledger(target,'123').load()
    ledger.save()
    path.write_text('用户重新编辑，甚至移除了文件头',encoding='utf-8')
    assert len(Ledger(target,'123').load().records) == 1
    assert path.read_text(encoding='utf-8') == '用户重新编辑，甚至移除了文件头'


@pytest.mark.parametrize('damage', ['corrupt', 'missing'])
def test_damaged_state_never_restarts_as_empty(tmp_path, damage):
    target, _, _ = setup(tmp_path)
    ledger = Ledger(target, '123').load()
    ledger.save()
    if damage == 'corrupt':
        ledger.path.write_text('{', encoding='utf-8')
    else:
        ledger.path.unlink()
    with pytest.raises(SyncError, match='state_'):
        Ledger(target, '123').load()


def test_unrecognized_existing_file_blocks_adoption(tmp_path):
    target, _, _ = setup(tmp_path)
    (target / 'invalid.md').write_text('正文没有元数据', encoding='utf-8')
    with pytest.raises(SyncError, match='existing_file_invalid'):
        Ledger(target, '123').load()


def test_unmatched_old_progress_blocks_adoption(tmp_path):
    target, _, _ = setup(tmp_path)
    (target.parent.parent / 'export-progress-123.json').write_text(
        json.dumps({'articles':{'exportedIds':['99']}}), encoding='utf-8')
    with pytest.raises(SyncError, match='legacy_inventory_mismatch'):
        Ledger(target, '123').load()


def test_writer_lock_excludes_second_process_or_handle(tmp_path):
    with writer_lock(tmp_path / 'sync'):
        with pytest.raises(SyncError, match='target_busy'):
            with writer_lock(tmp_path / 'sync'):
                pass
    with writer_lock(tmp_path / 'sync'):
        pass


def test_partial_images_resume_without_refetching_completed_image(tmp_path):
    target, identity, _ = setup(tmp_path)
    payload = render(identity, '标题', None,
        '<p>正文</p><img src="https://pic1.zhimg.com/a.jpg"><img src="https://pic1.zhimg.com/b.png">', '2026-11-14')
    ledger = Ledger(target, '123').load()
    ledger.save()
    exporter = Exporter(ledger)
    calls = []
    def first(url):
        calls.append(url)
        if url.endswith('b.png'):
            raise SyncError('network_error')
        return b'image-a'
    with pytest.raises(SyncError):
        exporter.finish(identity, payload, first, lambda:False)
    assert not list(target.glob('*.md'))
    assert not ledger.records
    exporter.finish(identity, exporter.staged(identity), lambda url:calls.append(url) or b'image-b', lambda:False)
    assert len(calls) == 3 and calls[0].endswith('a.jpg') and calls[-1].endswith('b.png')
    assert len(Ledger(target, '123').load().records) == 1


def test_publish_does_not_overwrite_conflicting_file(tmp_path):
    target, identity, payload = setup(tmp_path)
    (target / payload['filename']).write_text('本地修改', encoding='utf-8')
    with pytest.raises(SyncError, match='output_conflict'):
        Exporter(Ledger(target, '123')).finish(identity, payload, None, lambda:False)
    assert (target / payload['filename']).read_text(encoding='utf-8') == '本地修改'


def test_recover_published_markdown_before_ledger_commit(tmp_path, monkeypatch):
    target, identity, payload = setup(tmp_path)
    ledger = Ledger(target, '123').load()
    ledger.save()
    monkeypatch.setattr(ledger, 'complete', lambda *_: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        Exporter(ledger).finish(identity, payload, None, lambda:False)
    assert 'answer:2000991203269820437' in Ledger(target, '123').load().records


@pytest.mark.parametrize('url', ['http://127.0.0.1/a', 'file:///secret', 'https://zhimg.com.evil.test/a',
                                 'https://user:pass@pic1.zhimg.com/a', 'https://pic1.zhimg.com:123/a'])
def test_external_images_reject_untrusted_hosts(url):
    with pytest.raises((SyncError, ValueError)):
        image_url(url)


def test_markdown_preserves_code_links_formula_and_image_references(tmp_path):
    _, identity, _ = setup(tmp_path)
    result = render(identity, '标题', None,
        '<h2>标题</h2><p><strong>重点</strong> <a href="https://example.org">来源</a></p>'
        '<pre><code>print(1)</code></pre><img data-tex="x^2" src="https://www.zhihu.com/equation">'
        '<img src="https://pic1.zhimg.com/a.png"><script>bad()</script>', '2026-11-14')
    assert '**重点**' in result['content'] and '```' in result['content']
    assert '$x^2$' in result['content'] and 'bad()' not in result['content']
    assert len(result['assets']) == 1 and result['assets'][0]['path'] in result['content']
