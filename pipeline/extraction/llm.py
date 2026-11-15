"""Optional LLM gap-fill, used only where rule-based extraction left a field empty.

Guardrails (an LLM answer is discarded unless ALL hold):
1. The model must return a verbatim ``quote`` from the provided source text.
2. The quote must be found in the source after whitespace normalization.
3. Every extracted value must appear inside that quote (names) or be implied by
   role keywords in it (acquire/merge/sell).
Accepted values are stored with ``method="llm_verified"`` alongside the quote and source URL,
so they are always distinguishable from rule-based fields.

Provider: GitHub Models (OpenAI-compatible endpoint), which is free inside GitHub Actions
using the workflow's GITHUB_TOKEN with ``permissions: models: read``. Disabled unless MDR_LLM=1.
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests

from .. import config
from ..models import field
from .htmltext import flatten

log = logging.getLogger(__name__)

_PROMPT = """You extract facts from an SEC filing about a merger or acquisition.
The filing was made by "{filer}". Answer ONLY with JSON:
{{"filer_role": "target" | "acquirer" | "seller" | "unknown",
  "counterparty": "<exact name of the other company as written in the text, or empty>",
  "quote": "<one sentence copied EXACTLY from the text that supports both answers>"}}
If the text does not clearly support an answer, use "unknown" and an empty counterparty.

TEXT:
{text}
"""

_ROLE_WORDS = {
    "target": r"acquisition of|acquire|merge[ds]? with and into|wholly[- ]owned subsidiary of|be acquired",
    "acquirer": r"acquire|acquisition|purchase|merge[ds]? with and into",
    "seller": r"sale of|sell|sold|divest",
}


class _Budget:
    calls = 0


def enabled() -> bool:
    return config.LLM_ENABLED and bool(os.environ.get("GITHUB_TOKEN"))


def _ask(prompt: str) -> dict | None:
    if _Budget.calls >= config.LLM_MAX_CALLS_PER_RUN:
        return None
    _Budget.calls += 1
    resp = requests.post(
        config.LLM_ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
        json={"model": config.LLM_MODEL, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    return json.loads(m.group(0)) if m else None


def verify(answer: dict, source_text: str) -> bool:
    """True only if the quote is verbatim and supports every extracted value."""
    quote = flatten(answer.get("quote") or "")
    if len(quote) < 20 or quote not in flatten(source_text):
        return False
    cp = (answer.get("counterparty") or "").strip()
    if cp and cp not in quote:
        return False
    role = answer.get("filer_role")
    if role not in _ROLE_WORDS:
        return False
    return bool(re.search(_ROLE_WORDS[role], quote, re.I))


def fill_roles(text: str, filer: str, url: str) -> dict | None:
    """Return {"role": field, "counterparty": field, "model": str} or None."""
    if not enabled():
        return None
    excerpt = text[:12000]
    try:
        answer = _ask(_PROMPT.format(filer=filer, text=excerpt))
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("LLM gap-fill failed for %s: %s", url, exc)
        return None
    if not answer or not verify(answer, excerpt):
        log.info("LLM answer rejected by verification for %s", url)
        return None
    quote = flatten(answer["quote"])
    return {
        "role": field(answer["filer_role"], url, quote, "llm_verified"),
        "counterparty": field(answer.get("counterparty") or None, url, quote, "llm_verified"),
        "model": config.LLM_MODEL,
    }
