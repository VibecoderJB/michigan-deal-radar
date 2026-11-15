"""Turn filing HTML into plain text and pull rule-based excerpts from it."""

from __future__ import annotations

import html
import re

_SCRIPT_RE = re.compile(r"<(script|style|head|title)[^>]*>.*?</\1>", re.I | re.S)
_HIDDEN_RE = re.compile(r"<ix:header>.*?</ix:header>", re.I | re.S)
_BLOCK_RE = re.compile(r"</?(p|div|br|tr|li|h[1-6]|table)[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
# A period followed by a space, but not after common corporate abbreviations.
_SENTENCE_END_RE = re.compile(
    r"(?<!\bInc)(?<!\bCorp)(?<!\bCo)(?<!\bLtd)(?<!\bMr)(?<!\bMs)(?<!\bNo)(?<!\bU\.S)(?<!\bL\.P)\.\s"
)
_WS_RE = re.compile(r"[ \t\r\f\v ​]+")


def html_to_text(raw: str) -> str:
    """Strip tags/scripts, decode entities, normalize whitespace (keeps line breaks)."""
    if not raw:
        return ""
    cleaned = _HIDDEN_RE.sub(" ", raw)
    cleaned = _SCRIPT_RE.sub(" ", cleaned)
    cleaned = _BLOCK_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')
    lines = (_WS_RE.sub(" ", line).strip() for line in cleaned.split("\n"))
    return "\n".join(line for line in lines if line)


def flatten(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clip(value: str, limit: int = 400) -> str:
    """Trim to ``limit`` characters on a word/sentence boundary."""
    value = flatten(value)
    if len(value) <= limit:
        return value
    cut = value[:limit]
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(cut)]
    if ends and ends[-1] > limit * 0.6:
        return cut[: ends[-1]].rstrip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"
