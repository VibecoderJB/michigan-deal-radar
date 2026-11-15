"""Namespace-agnostic helpers for EDGAR XML documents."""

from __future__ import annotations

import xml.etree.ElementTree as ET


class ParseError(ValueError):
    """Raised when a filing document cannot be parsed."""


def parse_xml(text: str) -> ET.Element:
    """Parse XML and strip namespaces so lookups can use bare tag names."""
    if not text or not text.strip():
        raise ParseError("empty document")
    try:
        root = ET.fromstring(text.strip().encode("utf-8"))
    except ET.ParseError as exc:
        raise ParseError(f"invalid XML: {exc}") from exc
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def text(el: ET.Element | None, path: str, default: str | None = None) -> str | None:
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    value = found.text.strip()
    return value if value else default


def first_text(root: ET.Element, tag: str) -> str | None:
    """Text of the first element with ``tag`` anywhere in the tree."""
    for el in root.iter(tag):
        if el.text and el.text.strip():
            return el.text.strip()
    return None


def to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"true", "y", "yes", "1"}


def to_number(value: str | None) -> float | None:
    """Parse ``"1500000"`` / ``"1,500,000.00"``; return None for 'Indefinite' etc."""
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
