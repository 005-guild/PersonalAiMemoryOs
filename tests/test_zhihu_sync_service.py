"""Orchestration, offline preview, session failure and protected configuration."""

from contextlib import contextmanager
import threading
import time

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.configuration import SyncConfiguration, SyncConfigurationWrite
from app.services.zhihu_sync.runner import run_collection
from app.services.zhihu_sync.service import ZhihuSyncService
from app.services.zhihu_sync.storage import SyncError


class FakeBrowser:
    def __init__(self):
        self.items = [normalize_zhihu_url('https://www.zhihu.com/question/1/answer/2000991203269820437')]
        self.fetches = 0

    def collection(self, url):
        return self.items * 2

    def article(self, identity):
        self.fetches += 1
        return {'title':'测试', 'author':None, 'html':'<p>完整原文</p>'}

    def image(self, url):
        raise AssertionError('Unexpected image fetch')


def config(tmp_path, **kwargs):
    return SyncConfiguration(collection_url='https://www.zhihu.com/collection/123',
                             target_dir=str(tmp_path/'collection/articles'), **kwargs)


def test_preview_then_repeat_and_deleted_file_do_not_fetch_again(tmp_path):
    settings, browser = config(tmp_path), FakeBrowser()
    updates = []
    report = run_collection(settings,browser,lambda:False,updates.append,preview=True)
    assert report['total'] == report['would_create'] == 1
    assert browser.fetches == 0 and not (tmp_path/'collection').exists()
    assert run_collection(settings,browser,lambda:False,updates.append)['created'] == 1
    assert run_collection(settings,browser,lambda:False,updates.append)['skipped'] == 1
    next((tmp_path/'collection/articles').glob('*.md')).unlink()
    assert run_collection(settings,browser,lambda:False,updates.append)['skipped'] == 1
    assert browser.fetches == 1


def test_login_failure_does_not_create_success_ledger(tmp_path):
    browser = FakeBrowser()
    browser.collection = lambda _: (_ for _ in ()).throw(SyncError('login_required'))
    with pytest.raises(SyncError, match='login_required'):
        run_collection(config(tmp_path),browser,lambda:False,lambda _:None)
    assert not (tmp_path/'collection/.sync/state.json').exists()


def test_single_worker_and_cooperative_stop(settings, tmp_path):
    entered, release = threading.Event(), threading.Event()
    @contextmanager
    def factory(root, **kwargs):
        entered.set()
        while not release.wait(.01):
            if kwargs['cancelled']():
                raise SyncError('cancelled')
        yield FakeBrowser()
    service = ZhihuSyncService(settings, 'synthetic', factory)
    service.save(SyncConfigurationWrite(**config(tmp_path).model_dump(), expected_revision=service.describe()['revision']))
    service.start()
    try:
        service.submit('run')
        assert entered.wait(2)
        with pytest.raises(SyncError, match='sync_busy'):
            service.submit('run')
        service.request_stop()
        service.thread.join(3)
        assert not service.thread.is_alive()
        assert service.status['state'] == 'cancelled'
    finally:
        release.set()
        service.request_stop()
        service.thread.join(3)


def test_api_protects_writes_and_preserves_revision(settings, tmp_path):
    with TestClient(create_app(settings),base_url='http://127.0.0.1:18000') as client:
        url='/api/v1/settings/zhihu-sync'
        result=client.get(url)
        assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
        value=result.json()
        body={**config(tmp_path).model_dump(),'expected_revision':value['revision']}
        assert client.put(url,json=body).status_code == 403
        headers={'Origin':'http://127.0.0.1:18000','X-Configuration-Token':value['csrf_token']}
        saved=client.put(url,json=body,headers=headers)
        assert saved.status_code == 200 and not saved.json()['enabled']
        assert client.put(url,json=body,headers=headers).status_code == 409
        assert client.post(url+'/run',json={}).status_code == 403
        assert client.get(url,headers={'Origin':'https://evil.invalid'}).status_code == 403


@pytest.mark.parametrize('url',['https://evil.invalid/collection/1','https://www.zhihu.com/collection/1?secret=x',
                              'https://www.zhihu.com.evil.invalid/collection/1','http://www.zhihu.com/collection/1'])
def test_collection_url_validation(tmp_path,url):
    with pytest.raises(ValueError):
        SyncConfiguration(collection_url=url,target_dir=str(tmp_path))
