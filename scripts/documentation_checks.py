"""Pure Markdown checks; no Settings, private configuration or network access."""

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit


def blocks(text: str) -> list[tuple[str, str]]:
    result, marker, language, current = [], None, "", []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if match and marker is None:
            marker, language, current = match[1], match[2].strip(), []
        elif match and match[1][0] == marker[0] and len(match[1]) >= len(marker) and not match[2].strip():
            result.append((language, "\n".join(current)))
            marker = None
        elif marker is not None:
            current.append(line)
    if marker is not None:
        raise ValueError("Unclosed Markdown fence")
    return result


def without_fences(text: str) -> str:
    result, marker = [], None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if match and marker is None:
            marker = match[1]
        elif match and match[1][0] == marker[0] and len(match[1]) >= len(marker) and not match[2].strip():
            marker = None
        elif marker is None:
            result.append(line)
    return "\n".join(result)


def anchors(text: str) -> set[str]:
    text = without_fences(text)
    identifiers = set(re.findall(r'<a\s+id=[\"\']([^\"\']+)', text))
    counts = {}
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
        if match:
            label = re.sub(r"<[^>]*>", "", match[1]).lower()
            label = "".join(c for c in label if c in "-_ " or not unicodedata.category(c).startswith(("P", "S")))
            slug = label.replace(" ", "-")
            index = counts.get(slug, 0)
            counts[slug] = index + 1
            identifiers.add(slug + (f"-{index}" if index else ""))
    return identifiers


def check_links(root: Path, path: Path, text: str) -> int:
    count = 0
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", without_fences(text)):
        target = target.strip("<>")
        if urlsplit(target).scheme or target.startswith("//"):
            continue
        filename, _, anchor = target.partition("#")
        linked = (path.parent / unquote(filename)).resolve() if filename else path
        if not linked.is_relative_to(root.resolve()) or not linked.exists():
            raise ValueError(f"{path.name}: missing or external local link {target}")
        if anchor and (not linked.is_file() or unquote(anchor) not in anchors(linked.read_text(encoding="utf-8-sig"))):
            raise ValueError(f"{path.name}: missing anchor {target}")
        count += 1
    return count
