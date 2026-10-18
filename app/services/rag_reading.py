"""Build literal, ordered evidence windows over version-checked SQLite notes."""

import re
from uuid import UUID, uuid5

from app.vector.chunking import render_note

NAMESPACE = UUID("11a18662-d878-40ba-9cc4-ce14cce6d570")
CONTEXT_BUDGET = 12000


def body_offset(note):
    return len(render_note({**note, "body": ""}))


def sections(text):
    """Markdown headings outside fenced code. Retain every original character."""
    starts, offset, fence = [0], 0, None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None and re.match(r"^ {0,3}#{1,6}\s+", line) and offset:
            starts.append(offset)
        offset += len(line)
    return list(zip(starts, [*starts[1:], len(text)]))


def excerpt_ranges(note, matches, budget):
    text, offset = note["body"], body_offset(note)
    boundaries = sections(text)
    result, used = [], 0
    for match in matches:
        anchor = max(0, min(len(text) - 1, match["start"] - offset)) if text else 0
        start, end = next(((a, b) for a, b in boundaries if a <= anchor < b), (0, len(text)))
        # Preserve a whole section when possible. Huge sections use complete
        # neighbouring paragraphs around the hit, with an explicit partial scope.
        if end - start > min(6000, budget):
            start = max(start, anchor - 300)
            before = text.rfind("\n\n", max(0, start - 500), start)
            if before >= 0:
                start = before + 2
            end = min(end, start + min(6000, budget))
            after = text.rfind("\n\n", anchor, end)
            if after > anchor:
                end = after
        else:
            before = text.rfind("\n\n", max(0, start - 500), start - 1)
            after = text.find("\n\n", end, min(len(text), end + 500))
            start = before + 2 if before >= 0 else start
            end = after if after >= 0 else end
        if end <= start:
            continue
        merged = sorted([*result, (start, end)])
        joined = []
        for a, b in merged:
            if joined and a <= joined[-1][1]:
                joined[-1] = (joined[-1][0], max(b, joined[-1][1]))
            else:
                joined.append((a, b))
        size = sum(b-a for a, b in joined)
        if size <= budget:
            result, used = joined, size
        if used >= budget or len(result) >= 2:
            break
    return result


def build_reading(groups, budget=CONTEXT_BUDGET):
    contexts, notes = [], []
    for group in groups:
        note = group["note"]
        header = f"标题：{note['title']}\n摘要：{note['summary']}\n\n"
        available = budget - len(header)
        if available <= 0:
            break
        body = note["body"]
        full = len(body) <= 6000 and len(body) <= available
        ranges = [(0, len(body))] if full else excerpt_ranges(note, group["matches"], available)
        if not ranges and body:
            continue
        text = header + "\n\n[…]\n\n".join(body[a:b] for a, b in ranges)
        # Separators count against the same budget; omit a final range rather
        # than silently cropping a supplied evidence window.
        while len(text) > budget and len(ranges) > 1:
            ranges.pop()
            text = header + "\n\n[…]\n\n".join(body[a:b] for a, b in ranges)
        if len(text) > budget:
            continue
        scope = "full" if full else "sections"
        context_id = str(uuid5(NAMESPACE, f"{note['id']}:{note['version']}:{group['content_hash']}:{ranges}"))
        context = {key: note.get(key) for key in ("version", "title", "path", "source_id", "source", "source_ids", "sources")}
        context.update(chunk_id=context_id, context_id=context_id, knowledge_id=note["id"],
                       text=text, scope=scope, ranges=[list(r) for r in ranges],
                       content_hash=group["content_hash"], generation_id=group["generation_id"])
        contexts.append(context)
        notes.append({**{key: value for key, value in context.items() if key != "text"},
                      "score": group["score"], "matches": group["matches"],
                      "body_chars": len(body), "read_chars": sum(b-a for a,b in ranges)})
        budget -= len(text)
    return notes, contexts
