"""Load versioned prompts as files, and keep raw material in a data message."""

import hashlib
import json
from pathlib import Path

PROMPT_VERSION = "knowledge-v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "knowledge_v1.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def build_prompts(source_snapshot: dict) -> tuple[str, str]:
    data = {field: source_snapshot.get(field) for field in ("title", "author", "url", "content")}
    return SYSTEM_PROMPT, json.dumps(data, ensure_ascii=False, allow_nan=False)


def build_template_prompts(prompt_snapshot: dict, snapshots: list[dict]) -> tuple[str, str]:
    if prompt_snapshot["output_schema_version"] == 2:
        contract = (PROMPT_PATH.parent / "knowledge_v2_contract.md").read_text(encoding="utf-8")
    else:
        contract = SYSTEM_PROMPT
    system = prompt_snapshot.get("system_prompt") or prompt_snapshot["content"] + "\n\n" + contract
    return system, json.dumps({"sources": snapshots}, ensure_ascii=False, allow_nan=False)
