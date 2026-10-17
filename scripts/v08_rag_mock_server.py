"""Offline Embedding/Chat fixture recording the exact synthetic QA system prompt."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 404, {"status": "ok"})

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 * 1024:
                raise ValueError()
            if self.headers.get("Authorization") != "Bearer verification-only-key":
                raise ValueError()
            body = json.loads(self.rfile.read(size))
            if self.path == "/embeddings":
                inputs = body["input"]
                if not inputs or any(not isinstance(item, str) for item in inputs):
                    raise ValueError()
                result = {"data": [{"index": index, "embedding": [1.0, float(1 + item.count("索引")),
                    float(1 + item.count("备份")), float(1 + len(item) % 13)]} for index, item in enumerate(inputs)],
                    "usage": {"prompt_tokens": len(inputs) * 10, "total_tokens": len(inputs) * 10}}
                record = {"endpoint": "embeddings", "count": len(inputs)}
            elif self.path == "/chat/completions":
                system = body["messages"][0]["content"]
                payload = json.loads(body["messages"][-1]["content"])
                contexts = payload["contexts"]
                assert contexts
                context = contexts[0]
                answer = {"insufficient_evidence": False, "paragraphs": [{"text": "根据本次知识片段：" + context["text"][:100],
                    "citations": [{"chunk_id": context["chunk_id"], "quote": context["text"][:100]}]}]}
                result = {"choices": [{"message": {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
                    "finish_reason": "stop"}], "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}}
                record = {"endpoint": "chat", "system_prompt": system,
                    "system_hash": hashlib.sha256(system.encode("utf-8")).hexdigest(), "context_count": len(contexts)}
            else:
                self.respond(404, {"error": "unsupported_fixture_endpoint"})
                return
            with self.server.record_lock:
                with self.server.records.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
            if record["endpoint"] == "chat" and "V08_SNAPSHOT_STYLE_A" in record["system_prompt"]:
                time.sleep(2)
            self.respond(200, result)
        except (AssertionError, KeyError, TypeError, ValueError):
            self.respond(400, {"error": "invalid_fixture_request"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.records, server.record_lock = args.records, threading.Lock()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
