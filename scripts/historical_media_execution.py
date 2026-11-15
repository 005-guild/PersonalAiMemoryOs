"""Captured export evidence and offline recovery using the original sync runner."""

from collections import Counter
import hashlib
from pathlib import Path

from bs4 import BeautifulSoup

from app.services.zhihu_sync.export import image_url
from app.services.zhihu_sync.runner import run_collection
from app.services.zhihu_sync.storage import Ledger, SyncError, identity_key
from scripts.historical_media_inventory import audit_inventory, files_snapshot, matches


class CaptureBrowser:
    unsupported_count = unlisted_count = 0

    def __init__(self, browser, selected):
        self.browser, self.selected = browser, selected
        self.articles, self.images = {}, {}
        self.article_calls = self.image_calls = 0
        self.image_urls = []

    def collection(self, url):
        return self.selected

    def article(self, identity):
        self.article_calls += 1
        value = self.browser.article(identity)
        self.articles[identity_key(identity)] = value
        return value

    def image(self, url):
        self.image_calls += 1
        self.image_urls.append(url)
        value = self.browser.image(url)
        prior = self.images.get(url)
        if prior is not None and prior != value:
            raise RuntimeError('image_bytes_changed_during_verification')
        self.images[url] = value
        return value


class NoNetworkBrowser:
    unsupported_count = unlisted_count = 0

    def __init__(self, selected):
        self.selected = selected

    def collection(self, url):
        return self.selected

    def article(self, identity):
        raise AssertionError('Completed item requested its body')

    def image(self, url):
        raise AssertionError('Completed item requested an image')


class ReplayBrowser(CaptureBrowser):
    def __init__(self, captured, identity, *, fail_second=False):
        super().__init__(None, [identity])
        self.captured, self.fail_second = captured, fail_second

    def article(self, identity):
        self.article_calls += 1
        return self.captured.articles[identity_key(identity)]

    def image(self, url):
        self.image_calls += 1
        self.image_urls.append(url)
        if self.fail_second and self.image_calls == 2:
            raise SyncError('network_error')
        return self.captured.images[url]


def expected_urls(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('script, style, iframe, button, noscript'):
        tag.decompose()
    return [image_url(img.get('data-original') or img.get('data-actualsrc') or img.get('src') or '')
            for img in soup.find_all('img') if not img.get('data-tex')]


def verify_exports(target, captured, identities, coverage=()):
    entries, inventory = audit_inventory(target)
    assert not inventory['errors']
    by_key = {e['identity']: e for e in entries}
    assert set(by_key) == {identity_key(i) for i in identities}
    for identity in identities:
        key = identity_key(identity)
        urls = expected_urls(captured.articles[key]['html'])
        images = by_key[key]['images']
        assert len(images) == len(urls), 'Image reference omitted or added'
        for image, url in zip(images, urls):
            assert image['hash'] == hashlib.sha256(captured.images[url]).hexdigest(), 'Image bytes or order changed'
    for case in coverage:
        assert matches(by_key[case['identity']], case['case']), 'Actual exported coverage differs from selection'
    return {'articles_verified': len(entries), 'images_verified': inventory['physical_image_files'],
            'references_verified': sum(len(e['images']) for e in entries), 'coverage': list(coverage)}


def recover_interrupted(config, captured, identity, output):
    target = Path(output) / 'recovery/articles'
    target.mkdir(parents=True)
    isolated = config.model_copy(update={'target_dir': str(target), 'enabled': False})
    failing = ReplayBrowser(captured, identity, fail_second=True)
    first = run_collection(isolated, failing, lambda: False, lambda report: None)
    assert first['created'] == 0 and first['failed'] == 1
    assert not list(target.glob('*.md')) and not Ledger(target, config.collection_id).load().records
    retained = files_snapshot(target / 'images', timestamps=True)
    assert len(retained) == 1
    resumed = ReplayBrowser(captured, identity)
    second = run_collection(isolated, resumed, lambda: False, lambda report: None)
    assert second['created'] == 1 and second['failed'] == 0 and resumed.article_calls == 0
    urls = list(dict.fromkeys(expected_urls(captured.articles[identity_key(identity)]['html'])))
    assert Counter(resumed.image_urls) == Counter(urls[1:])
    assert all(files_snapshot(target / 'images', timestamps=True)[key] == value for key, value in retained.items())
    verify_exports(target, captured, [identity])
    published = files_snapshot(target, timestamps=True)
    requests = (resumed.article_calls, resumed.image_calls)
    third = run_collection(isolated, resumed, lambda: False, lambda report: None)
    assert third['created'] == 0 and third['skipped'] == 1 and third['failed'] == 0
    assert requests == (resumed.article_calls, resumed.image_calls) and files_snapshot(target, timestamps=True) == published
    return {'status': 'passed', 'failure': first, 'resume': second, 'repeat': third,
            'retained_image_refetched': False, 'resume_body_requests': resumed.article_calls}
