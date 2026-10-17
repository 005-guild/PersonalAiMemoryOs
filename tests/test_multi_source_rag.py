"""All source metadata follows current SQLite state without re-embedding text."""

import asyncio
import json

from app.services.content import ContentService
from app.services.rag_answer_output import render_answer
from test_rag_index import create_note, rig, update_note


def test_sources_return_in_search_and_citations_and_reorder_uses_cached_vectors(rig):
    with rig.database.session() as session:
        service = ContentService(session)
        first, second = [service.create_source({"title": title, "source_type": "manual"}) for title in ("first", "second")]
        session.commit()
    identities = [first["id"], second["id"]]
    note = create_note(rig, source_ids=identities)
    asyncio.run(rig.indexer.run_once())
    calls = len(rig.embeddings.calls)
    result = asyncio.run(rig.search.search("恢复演练"))
    assert result["items"] and result["items"][0]["source_ids"] == identities
    assert [item["id"] for item in result["items"][0]["sources"]] == identities
    item = result["items"][0]
    output = {"insufficient_evidence": False, "paragraphs": [{"text": "answer", "citations": [
        {"chunk_id": item["chunk_id"], "quote": item["text"][:10]}]}]}
    answer = render_answer(json.dumps(output), [item])
    assert answer["citations"][0]["source_ids"] == identities
    assert [source["id"] for source in answer["citations"][0]["sources"]] == identities
    update_note(rig, note, source_ids=list(reversed(identities)))
    calls = len(rig.embeddings.calls)
    asyncio.run(rig.indexer.run_once())
    assert len(rig.embeddings.calls) == calls
    changed = asyncio.run(rig.search.search("恢复演练"))["items"][0]
    assert changed["source_ids"] == list(reversed(identities)) and changed["source_id"] == second["id"]
