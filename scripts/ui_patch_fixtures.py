"""Synthetic API transport for UI-patch checks; never connects to application data."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

STAMP = "2026-10-17T00:00:00+00:00"


class PatchAPI:
    def __init__(self, count=3, *, deleted=()):
        self.notes = {}
        for index in range(count):
            note_id = f"20000000-0000-4000-8000-{index + 1:012d}"
            self.notes[note_id] = {
                "id": note_id, "title": f"笔记 {index + 1:02d}", "version": index + 1,
                "summary": "离线合成摘要", "body": f"原文 {index + 1}", "source_id": None,
                "category": "测试", "tags": [], "concepts": [], "sync_status": "synced",
                "created_at": STAMP, "updated_at": STAMP, "deleted_at": STAMP if index in deleted else None,
            }
        self.calls, self.pending = [], []
        self.failures = {}
        self.hold_lists = False
        self.profiles = {"enabled": True, "default_profile": "offline", "items": [{
            "id": "offline", "label": "离线布局验收", "protocol": "openai_chat",
            "model": "synthetic", "enabled": True, "configured": True}]}

    @staticmethod
    def reply(route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))

    def list_page(self, query):
        values = parse_qs(query)
        state, keyword = values.get("state", ["active"])[0], values.get("q", [""])[0]
        offset, limit = int(values.get("offset", ["0"])[0]), int(values.get("limit", ["20"])[0])
        notes = [dict(note) for note in self.notes.values()
                 if (state == "all" or bool(note["deleted_at"]) == (state == "deleted"))
                 and keyword in note["title"]]
        return {"items": notes[offset:offset + limit], "total": len(notes), "offset": offset, "limit": limit}

    def finish_list(self):
        route, query = self.pending.pop(0)
        self.reply(route, self.list_page(query))

    def handle(self, route):
        request = route.request
        parsed, method = urlsplit(request.url), request.method
        path = parsed.path
        entry = {"method": method, "path": path, "query": parsed.query}
        if method == "POST":
            entry["body"] = request.post_data_json
        self.calls.append(entry)
        if path == "/health":
            return self.reply(route, {"status": "ok", "database": "ok"})
        if path == "/api/v1/ui/knowledge":
            if self.hold_lists:
                self.pending.append((route, parsed.query))
                return
            return self.reply(route, self.list_page(parsed.query))
        if path == "/api/v1/ai/profiles":
            return self.reply(route, self.profiles)
        if path == "/api/v1/rag/index/status":
            return self.reply(route, {"enabled": True, "index_incomplete": False, "counts": {}})
        if path == "/api/v1/rag/search":
            return self.reply(route, {"items": [], "index_incomplete": False})
        if path == "/api/v1/rag/ask":
            return self.reply(route, {"answer": "知识库依据不足", "paragraphs": [], "citations": [],
                                     "insufficient_evidence": True, "index_incomplete": False,
                                     "profile_id": "offline", "model": "synthetic", "usage": {}})
        if path.startswith("/api/v1/knowledge/"):
            note_id = path.rsplit("/", 1)[-1]
            note = self.notes[note_id]
            if method == "GET":
                return self.reply(route, note)
            if method == "DELETE":
                version = int(parse_qs(parsed.query)["expected_version"][0])
                failure = self.failures.get(note_id)
                if failure == "abort_after_commit":
                    note.update(deleted_at=STAMP, version=note["version"] + 1)
                    return route.abort("failed")
                if failure == "abort":
                    return route.abort("failed")
                if version != note["version"]:
                    return self.reply(route, {"detail": "stale_version"}, 409)
                if isinstance(failure, int):
                    return self.reply(route, {"detail": "synthetic_failure"}, failure)
                note.update(deleted_at=STAMP, version=note["version"] + 1)
                return self.reply(route, note)
        return self.reply(route, {"detail": "Unexpected synthetic request: " + path}, 404)

    @property
    def deletions(self):
        return [item for item in self.calls if item["method"] == "DELETE"]
