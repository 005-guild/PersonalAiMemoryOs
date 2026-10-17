"""Measure fixed Chinese retrieval labels with real LOCAL BGE-M3; no generation."""

import argparse
import json
import logging
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import create_app
from app.repositories.migrations import upgrade_database
from benchmark_support import hardware_snapshot, timings
from local_rag_support import ForbiddenGeneration, MeasuredEmbedding, get_json, local_url, owned_cleanup, request
from local_rag_workflow import published, search
from prepare_quality_review import validate_corpus
from verification_support import isolated_proxy_environment
from verify_local_rag import prepare_settings
from v05_acceptance import storage_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    args = parser.parse_args()
    base, qdrant = local_url(args.embedding_url), local_url(args.qdrant_url)
    output = ROOT / ".cache/retrieval-quality" / uuid4().hex
    output.mkdir(parents=True)
    corpus = json.loads((ROOT / "examples/quality/retrieval-cn.json").read_text(encoding="utf-8"))
    validate_corpus(corpus)
    before = storage_fingerprint()
    measured, forbidden = MeasuredEmbedding(base), ForbiddenGeneration()
    report = {"status": "failed", "hardware": hardware_snapshot(), "cases": [], "generation_calls": 0, "quality_scope": "Fixed six-note Chinese corpus; no cited-answer quality claim",
              "platform": platform.platform(), "chunk_chars": 1200, "overlap": 200, "top_k": 5}
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    logging.basicConfig(level=logging.ERROR)
    try:
        with patch.dict(os.environ, environment, clear=True):
            models = get_json(base.removesuffix("/v1"), "/api/tags")["models"]
            model = next(m for m in models if m["name"] == "bge-m3:latest")
            report["model"] = model
            report["ollama"] = get_json(base.removesuffix("/v1"), "/api/version")
            report["qdrant"] = get_json(qdrant, "/")
            report["collections_before"] = get_json(qdrant, "/collections")["result"]["collections"]
            settings = prepare_settings(output, base, "bge-m3", model["digest"], qdrant).model_copy(update={"log_level": "ERROR"})
            upgrade_database(settings.database_url)
            with TestClient(create_app(settings, embedding_client=measured, model_client=forbidden)) as client:
                notes = {row["key"]: request(client, "POST", "/api/v1/knowledge", {k: v for k, v in row.items() if k != "key"})
                         for row in corpus["notes"]}
                published(client, len(notes))
                for case in corpus["queries"]:
                    start = time.perf_counter()
                    reply = search(client, case["query"])
                    elapsed = time.perf_counter() - start
                    hit_ids = [row["knowledge_id"] for row in reply["items"]]
                    expected = {notes[key]["id"] for key in case["relevant"]}
                    ranks = [hit_ids.index(identity) + 1 for identity in expected if identity in hit_ids]
                    report["cases"].append({**case, "hit_ids": hit_ids, "expected_ids": sorted(expected),
                        "recall_at_5": len(expected.intersection(hit_ids)) / len(expected),
                        "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                        "seconds": elapsed, "index_incomplete": reply["index_incomplete"]})
                assert all(not case["index_incomplete"] for case in report["cases"])
                report["recall_at_5"] = sum(c["recall_at_5"] for c in report["cases"]) / len(report["cases"])
                report["mrr_at_5"] = sum(c["reciprocal_rank"] for c in report["cases"]) / len(report["cases"])
                report["search_latency"] = timings([c["seconds"] for c in report["cases"]])
                report["ollama_running_models"] = get_json(base.removesuffix("/v1"), "/api/ps")
            report["status"] = "measured"
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        try:
            with patch.dict(os.environ, environment, clear=True):
                report["cleanup"] = owned_cleanup(output / "data/memory.db", qdrant)
                after = get_json(qdrant, "/collections")["result"]["collections"]
                assert report.get("collections_before") == after
        except Exception as error:
            report.update(status="failed", cleanup_error=str(error))
        report["embedding_requests"] = measured.records
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if forbidden.calls or not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output / "report.json"),
                      "recall_at_5": report.get("recall_at_5"), "mrr_at_5": report.get("mrr_at_5")}))
    return 0 if report["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
