"""Read AI-only dotenv values and rewrite chosen bindings without regex editing."""

from io import StringIO
import json

from dotenv.main import resolve_variables
from dotenv.parser import parse_stream

PREFIX = "MEMORY_OS_AI_"


def bindings(raw: bytes | None):
    return list(parse_stream(StringIO((raw or b"").decode("utf-8-sig"))))


def ai_values(raw: bytes | None) -> dict[str, str]:
    return selected_values(raw, (PREFIX,))


def selected_values(raw: bytes | None, prefixes: tuple[str, ...]) -> dict[str, str]:
    """Resolve interpolation while returning only the requested configuration groups."""
    values = resolve_variables(((item.key, item.value) for item in bindings(raw)
                                if item.key is not None), override=True)
    return {name.upper(): value for name, value in values.items()
            if name.upper().startswith(prefixes) and value is not None}


def keys_from(values: dict[str, str]) -> dict[str, str]:
    result = {}
    if "MEMORY_OS_AI_KEYS" in values:
        parsed = json.loads(values["MEMORY_OS_AI_KEYS"])
        if not isinstance(parsed, dict) or any(not isinstance(value, str) for value in parsed.values()):
            raise ValueError("Invalid key configuration.")
        result.update({str(ref).casefold(): value for ref, value in parsed.items()})
    result.update({name.removeprefix("MEMORY_OS_AI_KEYS__").casefold(): value
                   for name, value in values.items() if name.startswith("MEMORY_OS_AI_KEYS__")})
    return result


def rewrite(raw: bytes | None, updates: dict[str, str]) -> bytes:
    chunks, remaining = [], dict(updates)
    text = (raw or b"").decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    for item in bindings(raw):
        name = item.key.upper() if item.key is not None else None
        if name in updates:
            if name in remaining:
                chunks.append(name + "=" + json.dumps(remaining.pop(name), ensure_ascii=False) + newline)
            # Remove duplicate assignments of only the explicitly updated keys.
        else:
            chunks.append(item.original.string)
    if remaining and chunks and not chunks[-1].endswith(("\n", "\r")):
        chunks.append(newline)
    chunks.extend(name + "=" + json.dumps(value, ensure_ascii=False) + newline for name, value in remaining.items())
    return (b"\xef\xbb\xbf" if raw and raw.startswith(b"\xef\xbb\xbf") else b"") + "".join(chunks).encode("utf-8")
