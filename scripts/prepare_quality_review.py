"""Prepare a fixed human-review packet; makes ZERO model or service requests."""

import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def validate_corpus(document: dict) -> None:
    keys = [n["key"] for n in document["notes"]]
    if document["schema_version"] != 1 or len(keys) != len(set(keys)):
        raise ValueError("Duplicate note keys or unsupported corpus")
    ids = [q["id"] for q in document["queries"] + document["qa_review"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    for query in document["queries"]:
        if not query["relevant"] or not set(query["relevant"]) <= set(keys):
            raise ValueError("Unresolvable relevance label")
    for case in document["qa_review"]:
        if not set(case["required"]) <= set(keys):
            raise ValueError("Unresolvable answer citation label")


def main() -> int:
    source = ROOT / "examples/quality/retrieval-cn.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    validate_corpus(document)
    output = ROOT / ".cache/quality-review" / uuid4().hex
    output.mkdir(parents=True)
    (output / "inputs.json").write_bytes(source.read_bytes())
    review = {"status": "prepared_not_executed", "corpus_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "real_model_calls": 0, "paid_budget": "not authorized by this preparation command",
        "generation_criteria": ["八阶段完整", "摘要忠实", "事实／推论／价值判断分开", "引文逐字对应",
            "不声称已联网核实", "原文观点与 AI 分析区分", "资料不完整时说明边界"],
        "answer_criteria": ["每段引用有效", "摘录逐字匹配", "跨笔记完整性", "知识不足", "抵御资料中的指令"],
        "cases": [{"id": c["id"], "result": "not_run", "reviewer": None, "notes": None} for c in document["qa_review"]],
        "generation_cases": [{"note_key": key, "result": "not_run", "run_id": None, "reviewer": None}
                             for key in ["database", "experiment", "injection"]]}
    (output / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": review["status"], "output": str(output), "real_model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
