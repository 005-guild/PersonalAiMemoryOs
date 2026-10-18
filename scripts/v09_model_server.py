"""Local deterministic answer server; never forwards or reads credentials."""

from http.server import BaseHTTPRequestHandler
import json


class Handler(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.loads(payload["messages"][-1]["content"])
        item = data["contexts"][0]
        quote = "恢复演练" if "恢复演练" in item["text"] else item["text"].split("\n\n",1)[-1][:100]
        output = {"insufficient_evidence": False, "paragraphs": [{"text": "根据本次笔记概括：" + quote,
            "citations": [{"chunk_id": item["chunk_id"], "quote": quote}]}]}
        type(self).calls += 1
        raw = json.dumps({"choices": [{"message": {"content": json.dumps(output,ensure_ascii=False)},
                                      "finish_reason": "stop"}], "usage": {"completion_tokens": 30}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
