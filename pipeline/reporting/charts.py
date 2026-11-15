"""Dependency-free SVG charts for PDF reports.

Every chart carries a title, labelled axes with units, and a source note, matching the
dashboard's chart standard.
"""

from __future__ import annotations

from html import escape

NAVY = "#0B1F3A"
ACCENT = "#C8962E"
GRID = "#D9DEE6"
MUTED = "#5B6B82"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, 'Liberation Sans', 'DejaVu Sans', sans-serif"


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1
    import math
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def bar_chart(
    labels: list[str],
    values: list[float],
    *,
    title: str,
    y_label: str,
    x_label: str,
    source: str,
    fmt=lambda v: f"{v:,.0f}",
    width: int = 640,
    height: int = 260,
    highlight_last: bool = True,
) -> str:
    """Vertical bar chart as an inline SVG string."""
    left, right, top, bottom = 64, 16, 40, 58
    pw, ph = width - left - right, height - top - bottom
    vmax = _nice_max(max(values) if values else 1)
    n = max(1, len(values))
    slot = pw / n
    bw = min(42, slot * 0.62)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" font-family="{FONT}" role="img" aria-label="{escape(title)}">',
        f'<text x="0" y="16" font-size="13" font-weight="700" fill="{NAVY}">{escape(title)}</text>',
    ]
    for i in range(5):
        v = vmax * i / 4
        y = top + ph - ph * i / 4
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 3.5:.1f}" font-size="9" text-anchor="end" fill="{MUTED}">{escape(fmt(v))}</text>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        h = ph * (v / vmax) if vmax else 0
        x = left + slot * i + (slot - bw) / 2
        color = ACCENT if (highlight_last and i == n - 1) else NAVY
        parts.append(f'<rect x="{x:.1f}" y="{top + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{color}" rx="1.5"/>')
        if v:
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{top + ph - h - 4:.1f}" font-size="8.5" text-anchor="middle" fill="{NAVY}">{escape(fmt(v))}</text>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{top + ph + 13:.1f}" font-size="8.5" text-anchor="middle" fill="{MUTED}">{escape(lab)}</text>')
    parts.append(f'<text x="{left + pw / 2:.1f}" y="{height - 22}" font-size="9" text-anchor="middle" fill="{MUTED}">{escape(x_label)}</text>')
    parts.append(f'<text transform="translate(12 {top + ph / 2:.1f}) rotate(-90)" font-size="9" text-anchor="middle" fill="{MUTED}">{escape(y_label)}</text>')
    parts.append(f'<text x="0" y="{height - 4}" font-size="8" fill="{MUTED}">Source: {escape(source)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def hbar_chart(labels: list[str], values: list[float], *, title: str, x_label: str, source: str,
               fmt=lambda v: f"{v:,.0f}", width: int = 640, row: int = 22) -> str:
    """Horizontal bars (rankings, sector mix)."""
    left, right, top, bottom = 170, 40, 30, 40
    height = top + bottom + row * max(1, len(values))
    pw = width - left - right
    vmax = _nice_max(max(values) if values else 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" font-family="{FONT}" role="img" aria-label="{escape(title)}">',
        f'<text x="0" y="16" font-size="13" font-weight="700" fill="{NAVY}">{escape(title)}</text>',
    ]
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = top + i * row
        w = pw * v / vmax if vmax else 0
        parts.append(f'<text x="{left - 8}" y="{y + row * 0.62:.1f}" font-size="9.5" text-anchor="end" fill="{NAVY}">{escape(lab[:30])}</text>')
        parts.append(f'<rect x="{left}" y="{y + 4}" width="{w:.1f}" height="{row - 8}" fill="{NAVY if i else ACCENT}" rx="1.5"/>')
        parts.append(f'<text x="{left + w + 5:.1f}" y="{y + row * 0.62:.1f}" font-size="9" fill="{NAVY}">{escape(fmt(v))}</text>')
    parts.append(f'<text x="{left + pw / 2:.1f}" y="{height - 20}" font-size="9" text-anchor="middle" fill="{MUTED}">{escape(x_label)}</text>')
    parts.append(f'<text x="0" y="{height - 4}" font-size="8" fill="{MUTED}">Source: {escape(source)}</text>')
    parts.append("</svg>")
    return "".join(parts)
