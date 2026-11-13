import copy

import pytest

from app.services.zhihu_sync.collection_pages import CollectionPages
from app.services.zhihu_sync.storage import SyncError


def url(offset, limit=2):
    return f'https://www.zhihu.com/api/v4/collections/123/items?offset={offset}&limit={limit}'


def page(offset, ids, end=False):
    return {'paging': {'totals': 3, 'is_start': offset == 0, 'is_end': end, 'next': url(offset + 2)},
            'data': [{'content': {'type': 'answer', 'id': value}} for value in ids]}


def test_server_omission_requires_complete_chain_and_exact_ids():
    pages = CollectionPages('123')
    pages.record(url(0), page(0, ['2000991203269820437']))
    pages.record(url(2), page(2, ['2'], True))
    assert pages.unlisted(3, {('answer', '2000991203269820437'), ('answer', '2')}, 0) == 1


@pytest.mark.parametrize('damage', ['missing_page', 'wrong_ids', 'wrong_total', 'early_end', 'skipped_offset', 'duplicate_id', 'invalid_response'])
def test_unproven_gap_still_fails(damage):
    pages = CollectionPages('123')
    first, last = page(0, ['1']), page(2, ['2'], True)
    if damage == 'wrong_total':
        last['paging']['totals'] = 4
    elif damage == 'early_end':
        first['paging']['is_end'] = True
    elif damage == 'skipped_offset':
        first['paging']['next'] = url(4)
    elif damage == 'duplicate_id':
        last['data'][0]['content']['id'] = '1'
    pages.record(url(0), first)
    if damage != 'missing_page':
        pages.record(url(2), last)
    pages.invalid = damage == 'invalid_response'
    identities = {('answer', '1'), ('answer', '3' if damage == 'wrong_ids' else '2')}
    with pytest.raises(SyncError, match='collection_changed_or_incomplete'):
        pages.unlisted(3, identities, 0)


def test_changed_page_is_rejected():
    pages = CollectionPages('123')
    original = page(0, ['1'])
    pages.record(url(0), original)
    changed = copy.deepcopy(original)
    changed['data'][0]['content']['id'] = '2'
    with pytest.raises(ValueError):
        pages.record(url(0), changed)


def test_response_observer_records_bad_data_without_leaking_it():
    class Response:
        url = 'https://www.zhihu.com/api/v4/collections/123/items?offset=0&limit=2'
        status = 200
        def text(self):
            return 'private invalid upstream response'
    pages = CollectionPages('123')
    pages.observe(Response())
    assert pages.invalid and not pages.pages
