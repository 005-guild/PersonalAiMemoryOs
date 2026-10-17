"""Offline, deterministic Embedding and Chat endpoints for v0.5 acceptance only."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading


def embedding(text: str) -> list[float]:
    """Small predictable nonzero vectors; this is not a quality evaluation model."""
    return [1.0, float(1 + text.count("索引")), float(1 + text.count("备份")),
            float(1 + len(text) % 13)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def respond(self, status: int, value: dict) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self.respond(200 if self.path == "/health" else 404, {"status": "ok"})

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1_048_576:
                raise ValueError("invalid_size")
            body = json.loads(self.rfile.read(size))
            if self.headers.get("Authorization") != "Bearer verification-only-key":
                raise ValueError("synthetic_auth_required")
            path = self.path.split("?", 1)[0]
            if path == "/embeddings":
                inputs = body["input"]
                if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) for x in inputs):
                    raise ValueError("invalid_input")
                response = {"object": "list", "model": "v05-offline-embedding",
                            "data": [{"object": "embedding", "index": index, "embedding": embedding(value)}
                                     for index, value in enumerate(inputs)],
                            "usage": {"prompt_tokens": len(inputs) * 10, "total_tokens": len(inputs) * 10}}
                record = {"endpoint": "embeddings", "count": len(inputs)}
            elif path == "/chat/completions":
                context = json.loads(body["messages"][-1]["content"])
                fragments = context["contexts"]
                if fragments:
                    fragment = fragments[0]
                    quote = fragment["text"][:150]
                    result = {"insufficient_evidence": False, "paragraphs": [{
                        "text": "笔记中的相关记录：" + quote,
                        "citations": [{"chunk_id": fragment["chunk_id"], "quote": quote}],
                    }]}
                else:
                    result = {"insufficient_evidence": True, "paragraphs": []}
                response = {"id": "v05-offline-chat", "model": "v05-offline-chat", "choices": [{
                    "message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)},
                    "finish_reason": "stop",
                }], "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}}
                record = {"endpoint": "chat", "context_count": len(fragments)}
            else:
                self.respond(404, {"error": "unsupported_offline_endpoint"})
                return
            with self.server.record_lock:
                with self.server.records.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(record) + "\n")
            self.respond(200, response)
        except (AssertionError, KeyError, TypeError, ValueError):
            self.respond(400, {"error": "request_did_not_match_offline_contract"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--records", type=Path, required=True)
    args = parser.parse_args()
    args.records.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.records = args.records
    server.record_lock = threading.Lock()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
