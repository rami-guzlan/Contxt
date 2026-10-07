"""Front matter: the small YAML subset every note, skill and proposal file uses.

Supported, and nothing else:

    key: plain scalar            key: "double quoted"        key: 'single quoted'
    key: [a, b, "c d"]           key:                         key: >   (folded block)
                                   - list item                  key: |   (literal block)

Values stay strings (or lists of strings). The engine interprets them; the parser never
guesses types, so `review_every: 4` is "4" until a reader asks for an int.
"""
from __future__ import annotations

import re

_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:(.*)$")
_FENCE = "---"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return value


def _inline_list(value: str) -> list[str]:
    inner = value.strip()[1:-1]
    items, current, quote = [], "", None
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            items.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current)
    return [_unquote(item) for item in items if item.strip()]


def split(text: str):
    """(front matter lines or None, body). A file without a leading fence has no meta."""
    text = str(text or "").replace("\r\n", "\n").lstrip("﻿")
    if not text.startswith(_FENCE + "\n"):
        return None, text
    end = text.find("\n" + _FENCE, len(_FENCE))
    if end < 0:
        return None, text
    block = text[len(_FENCE) + 1:end]
    rest = text[end + len(_FENCE) + 1:]
    if rest.startswith("\n"):
        rest = rest[1:]
    return block.split("\n"), rest


def parse(text: str):
    """Return (meta, body, errors). Never raises on malformed input."""
    lines, body = split(text)
    if lines is None:
        return {}, body, []
    meta: dict = {}
    errors: list[str] = []
    key = None
    block_style = None
    block_lines: list[str] = []

    def close_block():
        nonlocal block_style, block_lines, key
        if block_style is None:
            return
        indent = min((len(line) - len(line.lstrip()) for line in block_lines if line.strip()),
                     default=0)
        stripped = [line[indent:] for line in block_lines]
        while stripped and not stripped[-1].strip():
            stripped.pop()
        if block_style.startswith("|"):
            meta[key] = "\n".join(stripped)
        else:
            paragraphs, current = [], []
            for line in stripped:
                if line.strip():
                    current.append(line.strip())
                elif current:
                    paragraphs.append(" ".join(current))
                    current = []
            if current:
                paragraphs.append(" ".join(current))
            meta[key] = "\n".join(paragraphs)
        block_style, block_lines = None, []

    for number, raw in enumerate(lines, 1):
        if block_style is not None:
            if raw.strip() == "" or raw.startswith((" ", "\t")):
                block_lines.append(raw)
                continue
            close_block()
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s?(.*)$", raw) or re.match(r"^-\s+(.*)$", raw)
        if item and key is not None:
            current = meta.get(key)
            if not isinstance(current, list):
                current = [] if current in (None, "") else [current]
            current.append(_unquote(item.group(1)))
            meta[key] = current
            continue
        match = _KEY.match(raw)
        if not match:
            errors.append(f"line {number}: cannot parse {raw.strip()[:60]!r}")
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block_style = value
            block_lines = []
            meta[key] = ""
        elif value.startswith("[") and value.endswith("]"):
            meta[key] = _inline_list(value)
        else:
            meta[key] = _unquote(value)
    close_block()
    return meta, body, errors


def _needs_quotes(value: str) -> bool:
    if value == "":
        return True
    if value != value.strip():
        return True
    if value[0] in "[{>|!&*#?%@`\"'-" and not value.startswith("--"):
        return value[0] != "-" or value.startswith("- ")
    return ": " in value or value.endswith(":") or " #" in value


def _scalar(value) -> str:
    text = str(value)
    if "\n" in text:
        return None  # rendered as a block by the caller
    if _needs_quotes(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def dump(meta: dict, body: str = "", order=None) -> str:
    """Serialize meta and body. `order` lists keys to write first, in that order."""
    keys = list(order or [])
    keys = [k for k in keys if k in meta] + sorted(k for k in meta if k not in keys)
    lines = [_FENCE]
    for key in keys:
        value = meta[key]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                rendered = _scalar(item)
                lines.append(f"  - {rendered if rendered is not None else item}")
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
            continue
        rendered = _scalar(value)
        if rendered is None:
            lines.append(f"{key}: |")
            lines.extend("  " + line if line else "" for line in str(value).split("\n"))
        else:
            lines.append(f"{key}: {rendered}")
    lines.append(_FENCE)
    text = "\n".join(lines) + "\n"
    body = str(body or "")
    if body:
        text += body if body.endswith("\n") else body + "\n"
    return text


def as_list(value) -> list[str]:
    """A front-matter field read as a list: missing -> [], scalar -> [scalar]."""
    if value in (None, "", "none"):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def as_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("true", "yes", "1", "on"):
        return True
    if text in ("false", "no", "0", "off"):
        return False
    return default
