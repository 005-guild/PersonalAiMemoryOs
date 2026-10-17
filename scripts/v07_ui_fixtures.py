"""Synthetic v0.7 API used by real Chromium acceptance, never a model or personal data."""
from copy import deepcopy
from urllib.parse import urlsplit, parse_qs
from uuid import UUID
from settings_ui_fixtures import SettingsUIAPI


def uid(number):
    return str(UUID(int=number))


class V07UIAPI(SettingsUIAPI):
    def __init__(self):
        super().__init__()
        self.document['desktop'] = {'restart_supported': True}
        self.sources = [{'id': uid(index + 1), 'title': f'资料 {index + 1:02d}', 'version': 1,
                         'author': f'作者 {index + 1}', 'url': None, 'source_type': 'manual',
                         'content': f'# 原始正文 {index + 1}\n\n完整来源正文。<script>window.__unsafeV07=1</script>\n![外图](https://invalid.example/image.png)',
                         'excerpt': f'原始资料摘要 {index+1}', 'deleted_at': None,
                         'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'} for index in range(45)]
        self.templates = [{'id': uid(100), 'version': 1, 'name': '完整笔记模板', 'description': '合成模板',
                           'content': '请忠实整理完整知识正文。', 'content_hash': 'fixture-hash', 'output_schema_version': 2,
                           'is_default': True, 'archived_at': None, 'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'}]
        self.batches = []
        self.notes = {uid(200): {'id': uid(200), 'version': 3, 'title': '多来源笔记', 'body': '原始笔记正文',
                                'summary': '', 'category': None, 'tags': [], 'concepts': [],
                                'source_ids': [uid(1), uid(2)], 'source_id': uid(1), 'deleted_at': None,
                                'sync_status': 'synced', 'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z'}}
        self.mutations = []
        self.fail_next = None
        self.body_gets = []
        self.restart_requests = 0
        self.hold_sources = False
        self.pending_sources = []
        self.hold_preview = False
        self.pending_previews = []
        self.abort_batch = False

    def handle(self, route):
        request = route.request
        parsed = urlsplit(request.url); path = parsed.path; query = parse_qs(parsed.query)
        method = request.method
        if path in ['/health', '/api/v1/settings/ai']:
            return super().handle(route)
        self.calls.append({'method': method, 'path': path})
        if method != 'GET':
            self.mutations.append({'method': method, 'path': path, 'body': deepcopy(request.post_data_json)})
            if self.fail_next:
                status = self.fail_next; self.fail_next = None
                return self.reply(route, {'detail': {'code': 'fixture_conflict'}}, status)
        if path == '/api/v1/desktop/restart':
            self.restart_requests += 1
            return self.reply(route, {'status': 'restarting'}, 202)
        if path == '/api/v1/ai/profiles':
            return self.reply(route, {'enabled': True, 'default_profile': 'deepseek', 'error_code': None,
                'items': [{'id': 'deepseek', 'label': '合成模型', 'model': 'no-model-called', 'protocol': 'openai_chat', 'enabled': True, 'configured': True}]})
        if path == '/api/v1/ui/sources':
            items = [source for source in self.sources if not source['deleted_at'] and query.get('q', [''])[0] in source['title']]
            offset = int(query.get('offset', [0])[0]); limit = int(query.get('limit', [20])[0])
            value={'items': [{key: value for key, value in source.items() if key != 'content'} for source in items[offset:offset+limit]], 'total': len(items), 'offset': offset, 'limit': limit}
            if self.hold_sources:self.pending_sources.append((route,value));return
            return self.reply(route,value)
        if path.startswith('/api/v1/sources/'):
            source = next(source for source in self.sources if source['id'] == path.rsplit('/', 1)[-1])
            self.body_gets.append(source['id'])
            if self.hold_preview:self.pending_previews.append((route,deepcopy(source)));return
            return self.reply(route, source)
        if path == '/api/v1/prompt-templates':
            if method == 'POST':
                value = {**deepcopy(self.templates[0]), **request.post_data_json, 'id': uid(100 + len(self.templates)), 'version': 1, 'is_default': False, 'archived_at': None}
                self.templates.append(value); return self.reply(route, value, 201)
            items = [item for item in self.templates if query.get('include_archived', ['false'])[0] == 'true' or not item['archived_at']]
            offset = int(query.get('offset', [0])[0]); limit = int(query.get('limit', [20])[0])
            return self.reply(route, {'items': items[offset:offset+limit], 'total': len(items), 'offset': offset, 'limit': limit})
        if path.startswith('/api/v1/prompt-templates/'):
            parts = path.split('/'); value = next(item for item in self.templates if item['id'] == parts[4])
            if len(parts) > 5:
                if parts[5] == 'revisions': return self.reply(route, {'items': [value]})
                if parts[5] == 'default':
                    for item in self.templates: item['is_default'] = False
                    value['is_default'] = True
                if parts[5] == 'archive': value['archived_at'] = '2026-01-01T00:00:00Z'
            elif method == 'PATCH': value.update({key: val for key, val in request.post_data_json.items() if key != 'expected_version'})
            if method != 'GET': value['version'] += 1
            return self.reply(route, value)
        if path == '/api/v1/processing/runs':
            return self.reply(route, {'items': [], 'total': 0, 'offset': int(query.get('offset', [0])[0]), 'limit': 20})
        if path == '/api/v1/processing/batches':
            if method == 'POST':
                if self.abort_batch:return route.abort('connectionreset')
                payload = request.post_data_json; snapshots = [deepcopy(next(source for source in self.sources if source['id'] == item['source_id'])) for item in payload['sources']]
                items = [[source['id']] for source in snapshots] if payload['mode'] == 'individual' else [[source['id'] for source in snapshots]]
                value = {**payload, 'id': uid(300 + len(self.batches)), 'version': 1, 'status': 'paused', 'profile_id': payload.get('profile_id', 'deepseek'), 'model': 'no-model-called',
                         'source_count': len(snapshots), 'item_count': len(items), 'source_snapshots': snapshots,
                         'counts': {'pending': len(items), 'running': 0, 'ready': 0, 'failed': 0, 'interrupted': 0, 'cancelled': 0},
                         'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
                         'items': [{'id': uid(400+index), 'position': index, 'status': 'pending', 'source_ids': sources, 'run_id': None, 'attempts': 0} for index, sources in enumerate(items)]}
                self.batches.append(value); return self.reply(route, value, 202)
            return self.reply(route, {'items': self.batches, 'total': len(self.batches), 'offset': 0, 'limit': 20})
        if path.startswith('/api/v1/processing/batches/'):
            parts = path.split('/'); value = next(item for item in self.batches if item['id'] == parts[5])
            if method == 'POST': value['version'] += 1
            if path.endswith('/cancel'): value['status'] = 'cancelled'
            return self.reply(route, value)
        if path.startswith('/api/v1/knowledge/'):
            parts = path.split('/'); value = self.notes[parts[4]]
            if method == 'PATCH': value.update({key: val for key,val in request.post_data_json.items() if key != 'expected_version'}); value['version'] += 1
            if method == 'POST' and path.endswith('/restore'):
                if 'source_ids' in request.post_data_json: value['source_ids'] = request.post_data_json['source_ids']
                value['deleted_at'] = None; value['version'] += 1
            return self.reply(route, value)
        if path == '/api/v1/ui/overview': return self.reply(route, {'sources': 45, 'knowledge': 1, 'ready_runs': 0, 'open_conflicts': 0})
        if path == '/api/v1/ui/knowledge': return self.reply(route, {'items': [], 'total': 0, 'offset': 0, 'limit': 20})
        if path == '/api/v1/sync/status': return self.reply(route, {'status': 'idle', 'errors': [], 'conflicts': []})
        if path.startswith('/api/v1/rag/'): return self.reply(route, {'enabled': False, 'items': [], 'status': 'disabled'})
        return self.reply(route, {'detail': {'code': 'unexpected_fixture_request'}}, 500)
