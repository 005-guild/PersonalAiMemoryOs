"""Strict citation contract and server-rendered answers from bounded contexts."""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.vector.errors import RagError


class CitationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    chunk_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=500)


class ParagraphOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=2000)
    citations: list[CitationOutput] = Field(min_length=1, max_length=10)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Answer must contain text.")
        return value


class AnswerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    insufficient_evidence: bool
    paragraphs: list[ParagraphOutput] = Field(max_length=20)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate output field.")
        result[key] = value
    return result


def render_answer(text: str, contexts: list[dict]) -> dict:
    try:
        document = AnswerOutput.model_validate(json.loads(text, object_pairs_hook=_unique))
        if document.insufficient_evidence != (not document.paragraphs):
            raise ValueError("Invalid evidence state.")
        available = {item["chunk_id"]: item for item in contexts}
        citations, paragraphs, labels = [], [], {}
        for paragraph in document.paragraphs:
            ids = []
            for reference in paragraph.citations:
                item = available.get(reference.chunk_id)
                if item is None or not reference.quote.strip() or reference.quote not in item["text"]:
                    raise ValueError("Citation does not occur in the supplied context.")
                key = (reference.chunk_id, reference.quote)
                if key not in labels:
                    labels[key] = len(citations) + 1
                    citations.append({
                        "citation_id": labels[key], "chunk_id": reference.chunk_id,
                        "quote": reference.quote,
                        **{field: item.get(field) for field in
                           ("knowledge_id", "version", "title", "path", "source_id", "source")},
                    })
                if labels[key] not in ids:
                    ids.append(labels[key])
            paragraphs.append({"text": paragraph.text, "citation_ids": ids})
        answer = "\n\n".join(p["text"] + " " + "".join(f"[{i}]" for i in p["citation_ids"])
                               for p in paragraphs)
        return {"insufficient_evidence": document.insufficient_evidence,
                "answer": answer or "知识库依据不足，无法回答这个问题。",
                "paragraphs": paragraphs, "citations": citations}
    except (ValueError, TypeError, KeyError, ValidationError, RecursionError):
        raise RagError(502, "invalid_qa_output") from None
