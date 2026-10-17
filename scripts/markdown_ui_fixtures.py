"""Offline browser import fixtures; no application database or provider traffic."""

import json
from urllib.parse import parse_qs, urlsplit


class MarkdownUIAPI:
    def __init__(self):
        self.calls, self.pending = [], []
        self.partial = False
        self.hold = False
        self.invalid_last = False
        self.malicious = False

    @staticmethod
    def reply(route, value, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value, ensure_ascii=False))

    def report(self, request):
        parsed = urlsplit(request.url)
        dry = parse_qs(parsed.query).get('dry_run', ['false'])[0] == 'true'
        payload = json.loads(request.post_data_buffer.decode('utf-8-sig'))
        files = payload.get('files', payload.get('items', []))
        rows = []
        for index, item in enumerate(files):
            invalid = self.invalid_last and index == len(files) - 1
            row = {'index': index, 'status': 'invalid' if invalid else 'would_create' if dry else 'created',
                   'reason': 'invalid_metadata' if invalid else 'new_source', 'resource_type': ['answer','article','pin'][index % 3],
                   'relative_path': item.get('relative_path'), 'title': '离线标题 ' + str(index + 1), 'author': '示例作者',
                   'url': 'https://www.zhihu.com/question/1/answer/' + str(index + 1),
                   'source_id': None if dry or invalid else f'10000000-0000-4000-8000-{index+1:012d}', 'version': None if dry or invalid else 1,
                   'differing_fields': ['content'] if invalid else [], 'matched_source_ids': [], 'warnings': [],
                   'errors': [{'field': 'content', 'message': '缺少有效元数据'}] if invalid else [],
                   'content': 'RAW_BODY_NEVER_DOWNLOAD', 'body': 'RAW_BODY_NEVER_DOWNLOAD'}
            if self.malicious:
                row.update(title='<img src=x onerror="window.__unsafeImport=1">', author='<script>evil</script>',
                           warnings=['<svg onload="window.__unsafeImport=2">'], url='javascript:alert(1)')
            rows.append(row)
        count = len(files)
        invalid_count = 1 if self.invalid_last and count else 0
        result = {'dry_run': dry, 'total': count, 'processed': count, 'created': 0 if dry else count-invalid_count,
                  'would_create': count-invalid_count if dry else 0, 'skipped': 0, 'invalid': invalid_count,
                  'failed': 0, 'items': rows, 'content': 'RAW_BODY_NEVER_DOWNLOAD'}
        if self.partial and not dry:
            result.update(processed=1, created=1, would_create=0, failed=1, invalid=0, items=rows[:1])
        return result

    def handle(self, route):
        request = route.request
        path = urlsplit(request.url).path
        if path == '/health':
            return self.reply(route, {'status': 'ok', 'database': 'ok'})
        if path.startswith('/api/v1/ui/'):
            return self.reply(route, {'items': [], 'total': 0, 'offset': 0, 'limit': 20})
        if path.startswith('/api/v1/imports/'):
            self.calls.append({'url': request.url, 'bytes': request.post_data_buffer})
            if self.hold:
                self.pending.append(route)
                return
            return self.finish(route)
        return self.reply(route, {'detail': 'Unexpected mock API'}, 404)

    def finish(self, route):
        report = self.report(route.request)
        if self.partial and 'dry_run=false' in route.request.url:
            return self.reply(route, {'detail': 'synthetic_partial_commit', 'report': report}, 503)
        return self.reply(route, report)
