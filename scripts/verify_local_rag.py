"""Verify real local BGE-M3 retrieval using an isolated SQLite/vault and owned collections.

Requires a running Ollama with bge-m3 and Qdrant 1.19.x. Does not install, pull,
stop services, use paid APIs, or modify the desktop's configuration or notes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
from uuid import uuid4

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repositories.migrations import upgrade_database
from app.vector.configuration import EmbeddingRegistry
from app.vector.qdrant import QdrantClient
from app.repositories.rag import collection_metadata
from local_rag_support import (ForbiddenGeneration, MeasuredEmbedding, database_audit,
    generations, get_json, json_file, local_url, owned_cleanup)
from local_rag_workflow import check_restart, run_workflow
from v05_acceptance import storage_fingerprint
from verification_support import PROJECT_VERSION, isolated_proxy_environment


def prepare_settings(workspace: Path, base_url: str, model: str, digest: str, qdrant_url: str):
    configuration = workspace / "config"
    configuration.mkdir()
    (configuration / "ai-providers.yml").write_text(
        "schema_version: 1\nprofiles: {}\n", encoding="utf-8")
    document = {"schema_version": 1, "default_profile": "local_bge_m3", "profiles": {
        "local_bge_m3": {"protocol": "openai_embeddings", "base_url": base_url,
            "model": model, "model_revision": digest, "dimension": 1024, "auth": "none",
            "batch_size": 1, "timeout_seconds": 180.0}}}
    (configuration / "embedding-providers.yml").write_text(yaml.safe_dump(document), encoding="utf-8")
    return Settings(_env_file=None, runtime_root=workspace,
        database_url=f"sqlite:///{(workspace / 'data/memory.db').as_posix()}",
        knowledge_dir="knowledge", sync_enabled=True, sync_interval=0.3,
        deletion_grace=1.0, ai_enabled=False, ai_keys={}, ai_config_file="config/ai-providers.yml",
        rag_enabled=True, embedding_config_file="config/embedding-providers.yml",
        embedding_default_profile="local_bge_m3", rag_qdrant_url=qdrant_url, rag_interval=0.5)


def markdown_report(report: dict) -> str:
    checks = report.get("workflow", {}).get("checks", [])
    return "\n".join([
        "# 本地 BGE-M3 与 Qdrant 隔离验收", "",
        f"- 结果：{report['status']}", f"- 应用：{report['application_version']}",
        f"- 模型：{report.get('model', {}).get('name', 'unavailable')}",
        f"- 模型摘要：{report.get('model', {}).get('digest', 'unavailable')}",
        f"- 真实本地 Embedding 请求：{len(report.get('embedding_requests', []))}",
        "- 真实文本生成／DeepSeek 调用：0", "- 仅自编样例；正式资料与笔记未用于测试。", "",
        *[f"- 通过：{check}" for check in checks], "",
        "本报告证明本地向量接口、示例检索与索引生命周期；不代表任意问题检索质量或真实生成回答质量。",
        "详细命中、耗时、用量、运行设备信息及清理结果见同目录 report.json。", "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--model", default="bge-m3")
    arguments = parser.parse_args()
    base_url, qdrant_url = local_url(arguments.embedding_url), local_url(arguments.qdrant_url)
    if arguments.model not in {"bge-m3", "bge-m3:latest"}:
        parser.error("This acceptance is specifically for BGE-M3 at its native 1024 dimensions.")
    if not base_url.endswith("/v1"):
        parser.error("--embedding-url must end in /v1.")
    workspace = PROJECT_ROOT / ".cache/local-rag-validation" / uuid4().hex
    workspace.mkdir(parents=True)
    database = workspace / "data/memory.db"
    before = storage_fingerprint()
    report = {"status": "failed", "application_version": PROJECT_VERSION,
        "embedding_url": base_url, "qdrant_url": qdrant_url,
        "generation_calls": 0, "external_model_calls": 0, "formal_before": before}
    measured, forbidden = MeasuredEmbedding(base_url), ForbiddenGeneration()
    started = time.monotonic()
    print(f"Evidence: {workspace}", flush=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    try:
        with patch.dict(os.environ, environment, clear=True):
            ollama_url = base_url.removesuffix("/v1")
            report["ollama"] = get_json(ollama_url, "/api/version")
            tags = get_json(ollama_url, "/api/tags")
            model = next((row for row in tags.get("models", [])
                if row.get("name") in {arguments.model, arguments.model + ":latest"}), None)
            if model is None:
                raise RuntimeError("BGE-M3 has not been downloaded to the local Ollama service.")
            report["model"] = model
            report["qdrant"] = get_json(qdrant_url, "/")
            report["shared_collections_before"] = get_json(qdrant_url, "/collections")["result"]["collections"]
            settings = prepare_settings(workspace, base_url, arguments.model, model["digest"], qdrant_url)
            upgrade_database(settings.database_url)
            resolved = EmbeddingRegistry(settings).resolve()
            reply = asyncio.run(measured.embed(resolved, ["本地向量接口验证：知识笔记支持语义检索。 "]))
            report["probe"] = {"count": len(reply.vectors), "dimensions": len(reply.vectors[0]), "usage": reply.usage}
            with TestClient(create_app(settings, embedding_client=measured, model_client=forbidden)) as client:
                report["workflow"] = run_workflow(client, workspace, measured)
                report["ollama_running_models"] = get_json(ollama_url, "/api/ps")
            # Simulate loss of this test's current remote collection only. A fresh
            # application must recover from SQLite vectors without model calls.
            current = next(row for row in generations(database) if row["status"] == "ready")
            asyncio.run(QdrantClient(qdrant_url).delete_collection(
                current["collection"], collection_metadata(current)))
            before_restart = measured.count
            with TestClient(create_app(settings, embedding_client=measured, model_client=forbidden)) as client:
                report["restart"] = check_restart(client, report["workflow"], measured)
            report["restart"]["total_embedding_calls_including_one_search"] = measured.count - before_restart
            assert report["restart"]["total_embedding_calls_including_one_search"] == 1
            report["workflow"]["checks"] += ["restart persistence", "missing collection restored from vector cache"]
            report["database"] = database_audit(database)
            assert report["database"]["integrity"] == "ok" and not report["database"]["foreign_key_errors"]
            assert report["database"]["counts"] == {
                "sources": 1, "knowledge": 3, "processing_runs": 0, "processing_batches": 0}
            assert forbidden.calls == 0
            report["status"] = "passed"
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
        (workspace / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Failed: {type(error).__name__}: {error}", flush=True)
    finally:
        try:
            # Keep the same local proxy bypass during cleanup, including errors.
            with patch.dict(os.environ, environment, clear=True):
                report["cleanup"] = {"removed_owned_collections": owned_cleanup(database, qdrant_url)}
                after = get_json(qdrant_url, "/collections")["result"]["collections"]
            report["cleanup"]["shared_collections_after"] = after
            owned = {row["collection"] for row in generations(database)}
            assert not owned.intersection(row["name"] for row in after)
            assert {row["name"] for row in report.get("shared_collections_before", [])}.issubset(
                row["name"] for row in after)
        except Exception as error:
            report["cleanup"] = {"error_type": type(error).__name__, "error": str(error)}
            report["status"] = "failed"
        report["generation_calls"] = forbidden.calls
        report["embedding_requests"] = measured.records
        report["seconds"] = round(time.monotonic() - started, 3)
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["formal_storage_unchanged"] or forbidden.calls:
            report["status"] = "failed"
        json_file(workspace / "report.json", report)
        (workspace / "验收报告.md").write_text(markdown_report(report), encoding="utf-8")
    print(f"Result: {report['status']}; report: {workspace / 'report.json'}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
