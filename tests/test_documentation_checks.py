from pathlib import Path

import pytest

from scripts.documentation_checks import anchors, blocks, check_links


def test_examples_ignore_shorter_fences_inside_literal():
    assert blocks("````markdown\n```python\nx\n```\n````") == [("markdown", "```python\nx\n```")]
    with pytest.raises(ValueError, match="Unclosed"):
        blocks("```json\n{}")
    with pytest.raises(ValueError, match="encoding"):
        blocks("?????????")


def test_duplicate_headings_and_explicit_anchors():
    assert {"中文标题", "中文标题-1", "custom"} <= anchors('# 中文标题\n# 中文标题\n<a id="custom"></a>')
    assert "ignored" not in anchors("```\n# ignored\n```")


def test_local_links_reject_missing_anchor_and_external_path(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# Hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    assert check_links(tmp_path, path, "[ok](#hello) [folder](docs/) [web](https://example.org)") == 2
    for target in ["missing.md", "#absent", "../outside.md"]:
        with pytest.raises(ValueError):
            check_links(tmp_path, path, f"[bad]({target})")
    assert check_links(tmp_path, path, "```\n[example](missing.md)\n```") == 0
