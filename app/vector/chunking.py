"""Deterministic, lossless character windows over a fixed note projection."""

import json

from app.vector.errors import RagError

CHUNKER_VERSION = "knowledge-char-v1"


def render_note(note: dict) -> str:
    """Exclude lifecycle, source identity, and path from semantic content."""
    sections = []
    for field in ("title", "summary", "category", "tags", "concepts", "body"):
        value = note.get(field)
        if field in {"tags", "concepts"}:
            value = json.dumps(value or [], ensure_ascii=False, separators=(",", ":"))
        else:
            value = value or ""
        sections.append(f"{field}:\n{value}")
    return "\n\n".join(sections)


def split_document(text: str, size: int = 1200, overlap: int = 200,
                   max_chars: int = 100_000, max_chunks: int = 200) -> list[dict]:
    if (type(size) is not int or type(overlap) is not int or size <= 0
            or overlap < 0 or overlap >= size or max_chars < 1 or max_chunks < 1):
        raise RagError(422, "rag_chunk_configuration_invalid")
    if len(text) > max_chars:
        raise RagError(422, "rag_document_too_large")
    result = []
    start = 0
    while start < len(text):
        if len(result) >= max_chunks:
            raise RagError(422, "rag_too_many_chunks")
        end = min(len(text), start + size)
        result.append({"ordinal": len(result), "text": text[start:end],
                       "start": start, "end": end})
        if end == len(text):
            break
        start = end - overlap
    return result
