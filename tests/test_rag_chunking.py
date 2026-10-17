import pytest

from app.vector.chunking import CHUNKER_VERSION, render_note, split_document
from app.vector.errors import RagError


def test_render_semantic_fields_only_and_stable_order():
    note = {"title": "中文", "body": "正文\n```python\nprint('hi')\n```", "tags": ["标签"],
            "concepts": ["概念"], "summary": "摘要", "category": "分类"}
    text = render_note(note)
    assert text.index("title:") < text.index("summary:") < text.index("body:")
    assert "中文" in text and "```python" in text
    assert text == render_note({**note, "source_id": "other", "version": 10, "path": "moved.md"})
    assert CHUNKER_VERSION


@pytest.mark.parametrize("length", [0, 1, 1200, 1201, 5000, 100000])
def test_lossless_windows_and_offsets(length):
    text = ("中文\n```code```" * 10000)[:length]
    chunks = split_document(text)
    assert all(chunk["text"] == text[chunk["start"]:chunk["end"]] for chunk in chunks)
    assert [chunk["ordinal"] for chunk in chunks] == list(range(len(chunks)))
    reconstructed = "".join(chunk["text"] if index == 0 else chunk["text"][200:]
                            for index, chunk in enumerate(chunks))
    assert reconstructed == text


@pytest.mark.parametrize("kwargs", [{"size": 0}, {"overlap": 1200}, {"overlap": -1},
                                     {"max_chars": 2}, {"size": 2, "overlap": 0, "max_chunks": 1}])
def test_limits_fail_without_silent_truncation(kwargs):
    with pytest.raises(RagError) as error:
        split_document("abcdef", **kwargs)
    assert error.value.status_code == 422
