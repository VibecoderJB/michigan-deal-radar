"""Print the latest data-quality report as Markdown (used for the GitHub Actions run summary)."""

from __future__ import annotations

from .. import config
from ..storage.store import read_json


def main() -> None:
    q = read_json(config.QUALITY_DIR / "latest.json", {}) or {}
    print("## Michigan Deal Radar: data-quality report\n")
    print("| Metric | Value |\n|---|---|")
    for key, label in (("new_deal_count", "New deals"), ("total_deals", "Total deals"), ("duplicates_merged", "Duplicate filings merged"),
                       ("flagged_for_review_count", "Flagged for review"), ("source_error_count", "Source errors"), ("evidence_events", "Evidence events")):
        print(f"| {label} | {q.get(key, 'n/a')} |")
    print(f"| Confidence | {q.get('confidence', {})} |")
    for name, src in (q.get("sources") or {}).items():
        print(f"\n**{name}**: {src.get('status')} (new: {src.get('new', 'n/a')}, errors: {src.get('errors', 0)})")
        for feed in src.get("feeds") or []:
            print(f"- {'OK' if feed['ok'] else 'FAILED'} {feed['name']}: {feed.get('items', 0)} items, {feed.get('kept', 0)} kept {feed.get('error', '')}")


if __name__ == "__main__":
    main()
