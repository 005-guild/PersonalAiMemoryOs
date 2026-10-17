"""Deterministic, stdlib-only model endpoint for isolated acceptance, never production."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

SOURCE_TEXT = "数据库索引可以减少查询扫描的数据量。索引也增加写入和存储成本。\n应根据实际查询验证索引效果。"
EVIDENCE = "索引也增加写入和存储成本。"
RESULT = {
    "title": "数据库索引的收益与成本",
    "summary": "索引有助于减少查询扫描，但带来写入和存储成本，应结合实际查询验证效果。",
    "category": "数据库技术",
    "tags": ["数据库", "索引"],
    "concepts": ["查询扫描", "写入成本"],
    "key_points": ["索引可以减少查询扫描的数据量。", "应根据实际查询验证索引效果。"],
    "opinions": [{
        "statement": "索引存在写入和存储成本。",
        "evidence": EVIDENCE,
        "analysis": "评估索引时应同时考虑查询收益与维护成本。",
    }],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Never log request bodies or authorization headers.
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
            if size < 1 or size > 1_048_576:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(size))
            # This server answers only our synthetic material, never arbitrary user input.
            def strings(value):
                if isinstance(value, str):
                    yield value
                    # User messages intentionally encode the source snapshot as
                    # JSON data, so decode that layer before checking newlines.
                    try:
                        decoded = json.loads(value)
                    except (ValueError, RecursionError):
                        return
                    if isinstance(decoded, (dict, list)):
                        yield from strings(decoded)
                elif isinstance(value, dict):
                    for nested in value.values():
                        yield from strings(nested)
                elif isinstance(value, list):
                    for nested in value:
                        yield from strings(nested)
            if not any(SOURCE_TEXT in value for value in strings(body)):
                raise ValueError("Expected the synthetic source in the request")
            text = json.dumps(RESULT, ensure_ascii=False)
            path = self.path.split("?", 1)[0]
            if path == "/chat/completions":
                protocol = "openai_chat"
                assert body["stream"] is False and body["messages"]
                assert self.headers.get("Authorization") == "Bearer verification-only-key"
                response = {"id": "mock-chat", "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}}
            elif path == "/responses":
                protocol = "openai_responses"
                assert body["input"] and body.get("stream", False) is False
                assert self.headers.get("Authorization") == "Bearer verification-only-key"
                response = {"id": "mock-responses", "status": "completed", "output": [{"type": "message", "status": "completed", "role": "assistant",
                            "content": [{"type": "output_text", "text": text}]}], "usage": {"input_tokens": 100, "output_tokens": 80, "total_tokens": 180}}
            elif path == "/messages":
                protocol = "anthropic_messages"
                assert body["messages"] and body["max_tokens"]
                assert self.headers.get("x-api-key") == "verification-only-key"
                assert self.headers.get("anthropic-version")
                response = {"id": "mock-claude", "type": "message", "role": "assistant", "model": "mock-model",
                            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 80}}
            elif path == "/models/mock-model:generateContent":
                protocol = "gemini_generate_content"
                assert body["contents"]
                assert self.headers.get("x-goog-api-key") == "verification-only-key"
                response = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
                            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 80, "totalTokenCount": 180}}
            else:
                self.respond(404, {"error": {"message": "Unsupported mock endpoint"}})
                return
            records = getattr(self.server, "records", None)
            if records:
                with records.open("a", encoding="utf-8") as output:
                    output.write(json.dumps({"protocol": protocol, "path": path}) + "\n")
            self.respond(200, response)
        except (AssertionError, KeyError, TypeError, ValueError):
            self.respond(400, {"error": {"message": "Mock request did not match the acceptance contract"}})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--records", type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.records = args.records
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
