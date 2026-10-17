"""Offline deterministic draft, answer and Embedding fixture for browser acceptance."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading


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
            if self.path == "/embeddings":
                inputs = body["input"]
                if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) for x in inputs):
                    raise ValueError("invalid_input")
                result = {"object": "list", "data": [{"index": index, "embedding": [
                    1.0, float(1 + text.count("索引")), float(1 + text.count("备份")),
                    float(1 + len(text) % 13)]} for index, text in enumerate(inputs)],
                    "usage": {"prompt_tokens": len(inputs) * 10, "total_tokens": len(inputs) * 10}}
                record = {"endpoint": "embeddings", "count": len(inputs)}
            elif self.path == "/chat/completions":
                context = json.loads(body["messages"][-1]["content"])
                if "contexts" in context:
                    fragments = context["contexts"]
                    result = {"insufficient_evidence": not bool(fragments), "paragraphs": []}
                    if fragments:
                        fragment = fragments[0]
                        quote = fragment["text"][:150]
                        result["paragraphs"] = [{"text": "笔记记录：" + quote, "citations": [
                            {"chunk_id": fragment["chunk_id"], "quote": quote}]}]
                    record = {"endpoint": "chat", "task": "answer", "context_count": len(fragments)}
                else:
                    content = context["content"]
                    if not isinstance(content, str) or "索引" not in content:
                        raise ValueError("synthetic_source_required")
                    evidence = "索引也增加写入和存储成本。"
                    if evidence not in content:
                        raise ValueError("synthetic_evidence_required")
                    result = {"title": "数据库索引的收益与成本", "summary": "索引减少扫描，同时增加写入和存储成本。",
                        "category": "数据库技术", "tags": ["数据库", "索引"], "concepts": ["查询扫描"],
                        "key_points": ["索引可以减少查询扫描的数据量。"], "opinions": [{
                            "statement": "应同时考虑收益与成本。", "evidence": evidence,
                            "analysis": "AI 分析：应根据实际查询验证效果。"}]}
                    record = {"endpoint": "chat", "task": "draft"}
                result = {"id": "v06-offline-chat", "choices": [{"message": {"role": "assistant",
                    "content": json.dumps(result, ensure_ascii=False)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}}
            else:
                self.respond(404, {"error": "unsupported_offline_endpoint"})
                return
            with self.server.record_lock:
                with self.server.records.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(record) + "\n")
            self.respond(200, result)
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
    server.records, server.record_lock = args.records, threading.Lock()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
