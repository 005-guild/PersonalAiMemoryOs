"""Self-authored Chinese fixtures for real local Embedding/Qdrant acceptance."""

from pathlib import Path

from verification_support import eventually, note_path
from local_rag_support import request

RAG = "/api/v1/rag"
NOTES = [
    {"title": "数据库索引的查询收益和维护成本", "category": "数据库",
     "summary": "索引加快查找，同时增加写入和存储成本。",
     "tags": ["数据库", "索引"], "concepts": ["查询性能"],
     "body": "数据库索引可以减少查询需要扫描的数据，帮助过滤和排序。\n"
             "每次新增、删除或更新记录时，也可能需要维护索引，因此会增加写入延迟和磁盘占用。\n"
             "应根据真实查询、执行计划和写入负载决定是否增加索引，不能认为索引越多越好。\n"
             "```sql\nCREATE INDEX idx_books_title ON books(title);\n```\n"},
    {"title": "备份需要恢复演练", "category": "数据安全",
     "summary": "确认备份可用需要实际恢复并检查数据。", "tags": ["备份", "恢复"],
     "body": "仅看到备份任务成功，不足以证明故障时能够恢复。\n"
             "应该把备份还原到隔离环境，检查关键记录和附件是否完整，并测量恢复所需时间。\n"
             "恢复演练不能覆盖生产文件，应保留恢复步骤、检查结果和失败原因。\n"},
    {"title": "书房植物浇水记录", "category": "生活记录", "tags": ["植物"],
     "summary": "观察盆土状态后再浇水。",
     "body": "书房窗边的盆栽使用独立托盘。每次浇水前查看盆土是否干燥，并记录日期。\n"
             "浇水后清理托盘积水。植物的位置和观察记录属于个人生活资料。\n"},
]
QUERIES = [
    ("数据库索引有什么收益和成本？", 0),
    ("让数据库查得更快，会不会拖慢新增和修改记录？", 0),
    ("怎么知道保存的数据副本在出故障时真的能还原？", 1),
]


def status(client):
    return request(client, "GET", RAG + "/index/status?summary_only=true")


def published(client, count: int, note_id=None, version=None, timeout=180):
    def ready():
        value = status(client)
        counts = value["counts"]
        if value["last_error"] or counts["failed"]:
            raise RuntimeError(f"Index failure: {value}")
        if value["running"] or counts["published"] != count or counts["pending"]:
            return None
        if note_id is not None:
            application = client.app
            def snapshot(repository):
                chunks = repository.valid_chunks(value["generation"]["id"])
                return any(row["knowledge_id"] == note_id and row["version"] == version
                           for row in chunks.values())
            if not application.state.rag_index.transaction(snapshot):
                return None
        return value
    return eventually(ready, timeout=timeout)


def search(client, query: str):
    return request(client, "POST", RAG + "/search", {"query": query, "top_k": 5})


def run_workflow(client, workspace: Path, measured):
    assert request(client, "GET", "/health") == {"status": "ok", "database": "ok"}
    eventually(lambda: status(client)["generation"], timeout=90)
    published(client, 0)
    before = measured.count
    source = request(client, "POST", "/api/v1/sources", {
        "title": "只保留在资料库的样例", "content": "SOURCE_ONLY_LOCAL_RAG_NOT_INDEXED：这段正文不应进入知识索引。"})
    assert search(client, "资料库里的原文") == {"items": [], "index_incomplete": False}
    assert measured.count == before, "Source-only query must not need a query vector without indexed notes."
    notes = [request(client, "POST", "/api/v1/knowledge", {**note, "source_id": source["id"]})
             for note in NOTES]
    published(client, len(notes))
    results = []
    for query, expected_index in QUERIES:
        result = search(client, query)
        assert result["items"] and result["items"][0]["knowledge_id"] == notes[expected_index]["id"], result
        assert not result["index_incomplete"]
        assert all("SOURCE_ONLY_LOCAL_RAG_NOT_INDEXED" not in row["text"] for row in result["items"])
        results.append({"query": query, "expected_knowledge_id": notes[expected_index]["id"], **result})

    first = notes[0]
    path = eventually(lambda: note_path(workspace / "knowledge", first["id"]))
    eventually(lambda: request(client, "GET", f"/api/v1/knowledge/{first['id']}")["sync_status"] == "synced")
    marker = "新增验证标记：每周记录慢查询并观察写入延迟。"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + marker + "\n", encoding="utf-8")
    current = eventually(lambda: (value if marker in value["body"] else None)
        if (value := request(client, "GET", f"/api/v1/knowledge/{first['id']}")) else None)
    published(client, len(notes), first["id"], current["version"])
    edited = search(client, "数据库索引写入成本")
    assert any(row["knowledge_id"] == first["id"] and marker in row["text"]
               and row["version"] == current["version"] for row in edited["items"])

    deleted = request(client, "DELETE", f"/api/v1/knowledge/{first['id']}?expected_version={current['version']}")
    # SQLite validation must filter a stale remote point immediately after deletion.
    assert all(row["knowledge_id"] != first["id"] for row in search(client, QUERIES[0][0])["items"])
    published(client, len(notes) - 1)
    eventually(lambda: not path.exists())
    restored = request(client, "POST", f"/api/v1/knowledge/{first['id']}/restore",
                       {"expected_version": deleted["version"]})
    published(client, len(notes), first["id"], restored["version"])
    assert search(client, QUERIES[0][0])["items"][0]["knowledge_id"] == first["id"]

    original_generation = status(client)["generation"]["id"]
    before = measured.count
    eventually(lambda: not status(client)["running"])
    request(client, "POST", RAG + "/index/rebuild", {})
    eventually(lambda: status(client)["generation"]["id"] != original_generation)
    rebuilt = published(client, len(notes))
    assert measured.count == before, "Unchanged content rebuild should reuse SQLite vector cache."
    # Generation requests are rejected before transport when AI is disabled.
    answer = client.post(RAG + "/ask", json={"question": QUERIES[0][0]})
    assert answer.status_code == 503 and answer.json()["detail"]["code"] == "ai_disabled", answer.text
    return {"source_id": source["id"], "knowledge_ids": [row["id"] for row in notes],
            "edited_id": first["id"], "edited_version": restored["version"], "marker": marker,
            "semantic_cases": results, "edited_search": edited, "final_index": rebuilt,
            "checks": ["finite nonzero 1024-dimensional vectors", "Chinese keyword top1",
                       "Chinese paraphrase top1", "Source excluded with zero Embedding calls",
                       "Markdown edit reindexed", "deleted content filtered immediately",
                       "restore", "unchanged rebuild reuses SQLite vectors", "AI disabled"]}


def check_restart(client, state, measured):
    before = measured.count
    value = published(client, len(state["knowledge_ids"]), state["edited_id"], state["edited_version"])
    assert measured.count == before, "Missing Qdrant collection must restore from cached vectors without new embedding."
    result = search(client, QUERIES[1][0])
    assert result["items"][0]["knowledge_id"] == state["edited_id"]
    assert state["marker"] in result["items"][0]["text"]
    return {"index": value, "search": result, "cache_restoration_embedding_calls": 0}
