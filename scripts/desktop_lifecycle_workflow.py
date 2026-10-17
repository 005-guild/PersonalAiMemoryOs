"""Use a latched local fake provider to verify native close drains a paid intent."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import threading
import time

import yaml

from desktop_verification_support import FrozenDesktop, attach_window
from verification_support import eventually


def check_inflight_close(playwright, root: Path, evidence: Path, source_id: str):
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            calls.append({"path": self.path, "model": payload.get("model")})
            entered.set()
            if not release.wait(40):
                self.send_error(504)
                return
            result = {"title": "关闭等待测试草稿", "summary": "索引减少查询扫描，并带来写入成本。",
                      "category": "技术", "tags": ["索引"], "concepts": [],
                      "key_points": ["索引既有收益，也有成本。"], "opinions": []}
            body = json.dumps({"id": "desktop-latched-mock", "object": "chat.completion",
                               "model": "desktop-latched", "choices": [{"index": 0,
                               "message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)},
                               "finish_reason": "stop"}], "usage": {"prompt_tokens": 40, "completion_tokens": 30, "total_tokens": 70}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    environment_file = root / ".env"
    config = root / "config/ai-providers.yml"
    old_environment, old_config = environment_file.read_bytes(), config.read_bytes()
    app = FrozenDesktop(root, evidence)
    response, errors = [], []
    try:
        environment_file.write_text("MEMORY_OS_AI_ENABLED=true\nMEMORY_OS_RAG_ENABLED=false\n", encoding="utf-8")
        config.write_text(yaml.safe_dump({"schema_version": 1, "default_profile": "desktop_mock", "profiles": {
            "desktop_mock": {"enabled": True, "protocol": "openai_chat", "base_url": f"http://127.0.0.1:{server.server_port}",
                             "model": "desktop-latched", "auth": "none", "response_format": "json_object",
                             "timeout_seconds": 30, "max_output_tokens": 1024}}}), encoding="utf-8")
        app.start()
        browser, page = attach_window(playwright, app)
        source = app.request("GET", "/api/v1/sources/" + source_id)

        def generate():
            try:
                response.append(app.request("POST", "/api/v1/processing/runs", {
                    "source_id": source_id, "expected_source_version": source["version"]}))
            except Exception as error:
                errors.append(str(error))

        request_thread = threading.Thread(target=generate, daemon=True)
        request_thread.start()
        assert entered.wait(20), "The frozen application never reached the isolated mock provider"
        app.request_close()
        runtime_path = root / ".cache/desktop/runtime.json"
        eventually(lambda: json.loads(runtime_path.read_text(encoding="utf-8")).get("status") == "stopping")
        assert app.process.poll() is None, "Closing killed the process before its in-flight provider request completed"
        assert not response and not errors
        page.screenshot(path=str(evidence / "desktop-draining-provider.png"), full_page=True)
        release.set()
        request_thread.join(timeout=35)
        assert not request_thread.is_alive() and not errors, errors
        assert response and response[0]["status"] == "ready", response
        run_id = response[0]["id"]
        app.wait_closed()
        connection = sqlite3.connect(root / "data/memory.db")
        try:
            assert connection.execute("SELECT status FROM processing_runs WHERE id=?", (run_id,)).fetchone()[0] == "ready"
            assert connection.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 1
        finally:
            connection.close()
        assert len(calls) == 1, calls
        return {"status": "passed", "mock_calls": len(calls), "real_model_calls": 0, "run_id": run_id,
                "draft_persisted": True, "knowledge_created": False, "drained_without_forced_kill": True}
    finally:
        release.set()
        app.stop()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)
        environment_file.write_bytes(old_environment)
        config.write_bytes(old_config)
