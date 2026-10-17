"""Diverse synthetic records for full-dataset Source-group sorting checks."""

from source_group_ui_fixtures import GroupUIAPI, STAMP


class SortUIAPI(GroupUIAPI):
    def __init__(self):
        super().__init__()
        self.records.clear()
        self.expected_groups = []
        for index in range(45):
            title = f'排序标题 {index:02d}'
            count = index % 5 + 1
            kind = ['zeta', 'alpha,zz', 'beta'][index % 3]
            stamp = f'2026-10-{(index * 7) % 28 + 1:02d}T{index % 24:02d}:00:00+00:00'
            self.expected_groups.append({'title': title, 'count': count, 'kind': kind, 'stamp': stamp})
            for member in range(count + 1):
                identifier = f'30000000-0000-4000-8000-{index * 10 + member + 1:012d}'
                deleted = member == count
                self.records[identifier] = {'id': identifier, 'title': title,
                    'source_type': '0-deleted' if deleted else kind if member == 0 else 'zz-last',
                    'author': f'作者 {index}-{member}', 'url': None, 'content': f'{title} 独立原文 {member}。',
                    'version': 1, 'created_at': STAMP, 'updated_at': '2026-11-01T00:00:00+00:00' if deleted else stamp,
                    'deleted_at': STAMP if deleted else None}

    def expected_titles(self, sort_by, order, *, state='active', query=''):
        groups = [group for group in self.expected_groups if query in group['title']]
        keys = {'title': lambda group: group['title'],
                'source_count': lambda group: group['count'] + (state == 'all') if state != 'deleted' else 1,
                'source_type': lambda group: group['kind'] if state == 'active' else '0-deleted',
                'updated_at': lambda group: group['stamp'] if state == 'active' else '2026-11-01T00:00:00+00:00'}
        return [group['title'] for group in sorted(groups, key=keys[sort_by], reverse=order == 'desc')]
