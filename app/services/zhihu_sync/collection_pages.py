"""Verify gaps using collection responses already requested by the visible site.

No additional endpoint calls are made. A lower DOM count alone never proves
that pagination completed; every server page and supported ID must agree.
"""

import json
import re
from urllib.parse import parse_qs, urlsplit

from app.services.zhihu_sync.storage import SyncError


class CollectionPages:
    def __init__(self, collection_id):
        self.path = f'/api/v4/collections/{collection_id}/items'
        self.pages = {}
        self.contents = {}
        self.invalid = False

    def position(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.zhihu.com' or parsed.path != self.path:
            raise ValueError()
        query = parse_qs(parsed.query)
        values = []
        for name in ('offset', 'limit'):
            entries = query[name]
            if len(entries) != 1 or not re.fullmatch(r'[0-9]+', entries[0]):
                raise ValueError()
            values.append(int(entries[0]))
        offset, limit = values
        if not 0 <= offset <= 10_000_000 or not 1 <= limit <= 100:
            raise ValueError()
        return offset, limit

    def observe(self, response):
        parsed = urlsplit(response.url)
        if parsed.netloc != 'www.zhihu.com' or parsed.path != self.path:
            return
        try:
            if response.status != 200:
                raise ValueError()
            raw = response.text()
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError()
            self.record(response.url, json.loads(raw))
        except Exception:
            # Browser event callbacks must not leak server text or session data.
            self.invalid = True

    def record(self, url, value):
        offset, limit = self.position(url)
        paging, items = value['paging'], value['data']
        if (type(paging['totals']) is not int or type(paging['is_end']) is not bool
                or type(paging['is_start']) is not bool or not isinstance(items, list) or len(items) > limit):
            raise ValueError()
        keys = []
        for item in items:
            content = item['content']
            kind, identifier = content['type'], content['id']
            if (kind not in {'answer', 'article', 'pin', 'video', 'zvideo'}
                    or type(identifier) not in {str, int} or not re.fullmatch(r'[1-9][0-9]*', str(identifier))):
                raise ValueError()
            keys.append((kind, str(identifier)))
        next_position = None if paging['is_end'] else self.position(paging['next'])
        page = (paging['totals'], paging['is_start'], paging['is_end'], next_position, tuple(keys))
        if (offset, limit) in self.pages and self.pages[offset, limit] != page:
            raise ValueError()
        self.pages[offset, limit] = page
        self.contents.update({(item['content']['type'], str(item['content']['id'])): item['content'] for item in items})

    def unlisted(self, expected, identities, unsupported_count):
        try:
            starts = [position for position in self.pages if position[0] == 0]
            if self.invalid or len(starts) != 1:
                raise ValueError()
            position, visited, keys = starts[0], set(), set()
            while True:
                if position in visited:
                    raise ValueError()
                visited.add(position)
                offset, limit = position
                total, is_start, is_end, following, page_keys = self.pages[position]
                if (total != expected or is_start != (offset == 0)
                        or len(set(page_keys)) != len(page_keys) or keys.intersection(page_keys)):
                    raise ValueError()
                keys.update(page_keys)
                if is_end:
                    if not offset <= expected <= offset + limit:
                        raise ValueError()
                    break
                if following != (offset + limit, limit) or offset + limit >= expected:
                    raise ValueError()
                position = following
            supported = {key for key in keys if key[0] in {'answer', 'article', 'pin'}}
            if (visited != set(self.pages) or supported != set(identities)
                    or len(keys) - len(supported) != unsupported_count or len(keys) > expected):
                raise ValueError()
            return expected - len(keys)
        except (ValueError, KeyError, TypeError):
            raise SyncError('collection_changed_or_incomplete') from None
