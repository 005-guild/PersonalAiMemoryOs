"""Bounded, duplicate-free YAML metadata; errors never expose source lines."""

import re

import yaml
from yaml.events import AliasEvent

MAX_FRONTMATTER_CHARS = 64 * 1024
OPENING = re.compile(r"\A\ufeff?---[ \t]*(?:\r\n|\n)")
CLOSING = re.compile(r"^---[ \t]*(?:\r?\n|\Z)", re.MULTILINE)


class ExportLoader(yaml.SafeLoader):
    def __init__(self, stream):
        super().__init__(stream)
        self.depth = self.node_count = 0

    def compose_node(self, parent, index):
        self.depth += 1
        self.node_count += 1
        try:
            if self.depth > 16 or self.node_count > 2048 or self.check_event(AliasEvent):
                raise yaml.YAMLError("Unsupported metadata structure.")
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str) or key in mapping:
                raise yaml.YAMLError("Metadata keys must be unique strings.")
            mapping[key] = self.construct_object(value_node, deep=True)
        return mapping


def split_export(content: str) -> tuple[dict, str]:
    """Slice after the closing delimiter; never normalize source body newlines."""
    opening = OPENING.match(content)
    closing = CLOSING.search(content, opening.end()) if opening else None
    if closing is None or closing.start() - opening.end() > MAX_FRONTMATTER_CHARS:
        raise ValueError("invalid_frontmatter")
    try:
        metadata = yaml.load(content[opening.end():closing.start()], Loader=ExportLoader)
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise ValueError("invalid_frontmatter") from None
    if not isinstance(metadata, dict):
        raise ValueError("invalid_frontmatter")
    return metadata, content[closing.end():]
