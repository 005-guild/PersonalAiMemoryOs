"""Local synthetic Chat endpoint for v0.7 browser acceptance; never calls an external API."""
from http.server import BaseHTTPRequestHandler
import json
from threading import Lock


class Handler(BaseHTTPRequestHandler):
    calls = []
    lock = Lock()

    def log_message(self, *args):
        return

    def do_POST(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            snapshots = json.loads(payload['messages'][-1]['content'])['sources']
            assert snapshots and all(source['title'].startswith('v07 合成来源') for source in snapshots)
            result = {'title': '多来源完整笔记', 'summary': '合成资料用于验证批次生成及来源关联。', 'category': '工程验收',
                      'tags': ['合成测试'], 'concepts': ['版本控制'],
                      'body': '# 完整知识正文\n\n## 核心分析\n\n每篇资料有独立来源。\n\n## 实践结论\n\n保存版本与精确引用。',
                      'source_quotes': [{'source_id': source['id'], 'quote': source['content'][:30]} for source in snapshots]}
            with self.lock:
                self.calls.append({'source_count': len(snapshots), 'max_tokens': payload.get('max_tokens', payload.get('max_completion_tokens'))})
            response = {'choices': [{'message': {'content': json.dumps(result, ensure_ascii=False)}, 'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 100, 'completion_tokens': 200, 'total_tokens': 300}}
            status = 200
        except (KeyError, ValueError, AssertionError, TypeError):
            response = {'error': 'synthetic_input_required'}; status = 400
        body = json.dumps(response, ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type', 'application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
