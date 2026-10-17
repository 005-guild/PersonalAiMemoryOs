"""Synthetic configuration transport; never reads personal configuration or calls a model."""

from copy import deepcopy
import json
from urllib.parse import urlsplit


def configuration():
    common = {'label': None, 'enabled': True, 'auth': 'auto', 'response_format': 'prompt',
              'max_output_tokens': 4096, 'timeout_seconds': 90.0, 'token_limit_field': 'max_tokens',
              'anthropic_version': '2023-06-01', 'extra_body': {}}
    profiles = [
        {**common, 'id': 'deepseek', 'label': 'DeepSeek <img src=x onerror=window.__unsafeSettings=1>',
         'protocol': 'openai_chat', 'base_url': 'https://api.deepseek.com', 'model': 'fixture-chat',
         'api_key_ref': 'deepseek', 'response_format': 'json_object',
         'extra_body': {'thinking': {'type': 'disabled'}, 'custom': ['中文', {'nested': True}]}},
        {**common, 'id': 'responses', 'label': 'Responses', 'protocol': 'openai_responses',
         'base_url': 'https://api.example.invalid/v1', 'model': 'fixture-responses', 'api_key_ref': 'openai',
         'extra_body': {'reasoning': {'effort': 'low'}}},
        {**common, 'id': 'claude', 'label': 'Claude', 'protocol': 'anthropic_messages',
         'base_url': 'https://claude.example.invalid/v1', 'model': 'fixture-claude', 'api_key_ref': 'anthropic', 'auth': 'x_api_key'},
        {**common, 'id': 'gemini', 'label': 'Gemini', 'protocol': 'gemini_generate_content',
         'base_url': 'https://gemini.example.invalid/v1beta', 'model': 'fixture-gemini', 'api_key_ref': 'gemini', 'auth': 'x_goog_api_key'},
    ]
    return {'revision': 'revision-1', 'editable': True, 'read_only_reason': None, 'restart_required': False,
            'csrf_token': 'synthetic-csrf-token', 'enabled': False, 'default_profile': 'deepseek', 'profiles': profiles,
            'keys': [{'ref': ref, 'configured': ref in ['deepseek', 'gemini'], 'environment_managed': ref == 'gemini'}
                     for ref in ['deepseek', 'openai', 'anthropic', 'gemini']], 'environment_overrides': [],
            'locations': {'runtime_root': 'D:\\合成便携目录', 'config_directory': 'D:\\合成便携目录\\config',
                          'data_directory': 'D:\\合成便携目录\\data', 'database_file': 'D:\\合成便携目录\\data\\memory.db',
                          'knowledge_directory': 'D:\\合成便携目录\\knowledge',
                          'ai_config_file': 'D:\\合成便携目录\\config\\ai-providers.yml', 'env_file': 'D:\\合成便携目录\\.env'},
            'active': {'enabled': False, 'default_profile': 'deepseek'}}


class SettingsUIAPI:
    def __init__(self):
        self.document = configuration()
        self.calls, self.payloads, self.pending_gets, self.pending_puts = [], [], [], []
        self.hold_get = self.hold_put = False
        self.next_error = None

    @staticmethod
    def reply(route, value, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value, ensure_ascii=False))

    def complete_get(self):
        self.reply(self.pending_gets.pop(0), self.document)

    def complete_put(self):
        route, payload = self.pending_puts.pop(0)
        self.document.update({key: deepcopy(payload[key]) for key in ['enabled', 'default_profile', 'profiles']})
        for update in payload['key_updates']:
            key = next((key for key in self.document['keys'] if key['ref'].lower() == update['ref'].lower()), None)
            if key: key['configured'] = True
            else: self.document['keys'].append({'ref': update['ref'], 'configured': True, 'environment_managed': False})
        self.document.update(revision='revision-' + str(len(self.payloads) + 1), restart_required=True)
        self.reply(route, self.document)

    def handle(self, route):
        request = route.request; path = urlsplit(request.url).path
        self.calls.append({'method': request.method, 'path': path})
        if path == '/health': return self.reply(route, {'status': 'ok', 'database': 'ok'})
        if path == '/api/v1/settings/ai':
            if request.method == 'GET':
                if self.hold_get: self.pending_gets.append(route); return
                return self.reply(route, self.document)
            if request.method == 'PUT':
                payload = request.post_data_json
                self.payloads.append({'body': deepcopy(payload), 'token': request.headers.get('x-configuration-token')})
                if self.next_error:
                    status, detail = self.next_error; self.next_error = None
                    return self.reply(route, {'detail': detail}, status)
                self.pending_puts.append((route, payload))
                if not self.hold_put: self.complete_put()
                return
        if path == '/api/v1/ui/knowledge': return self.reply(route, {'items': [], 'total': 0, 'offset': 0, 'limit': 20})
        return self.reply(route, {'detail': {'code': 'unexpected_fixture_request'}}, 500)
