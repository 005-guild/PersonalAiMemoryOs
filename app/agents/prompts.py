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
