"""Data-quality report written after every pipeline run (``data/quality/latest.json``)."""

from __future__ import annotations

from collections import Counter

from ..models import is_disclosed, val

KEY_FIELDS = {
    "announcement_date": lambda d: d.get("announcement_date"),
    "status": lambda d: d.get("status"),
    "target.name": lambda d: (d.get("target") or {}).get("name"),
    "target.county": lambda d: (d.get("target") or {}).get("county"),
    "target.gics_sector": lambda d: (d.get("target") or {}).get("gics_sector"),
    "acquirer.name": lambda d: (d.get("acquirer") or {}).get("name"),
    "acquirer.type": lambda d: (d.get("acquirer") or {}).get("type"),
    "deal_value": lambda d: next((f for f in ((d.get("financials") or {}).get(k) for k in ("enterprise_value", "transaction_value", "equity_value")) if is_disclosed(f)), None),
    "rationale": lambda d: d.get("rationale"),
}


def quality_report(
    deals: list[dict],
    previous_ids: set[str],
    evidence_count: int,
    run_errors: list[dict],
    sources: dict,
    v1_records: list[set[str]] | None = None,
    evidence_ids: set[str] | None = None,
) -> dict:
    ma = [d for d in deals if d.get("category") == "M&A"]
    multi_source = [d for d in deals if len(d.get("sources") or []) > 1]
    missing = {}
    for name, getter in KEY_FIELDS.items():
        pool = ma if name in ("acquirer.name", "acquirer.type", "deal_value", "rationale") else deals
        n_missing = sum(1 for d in pool if not is_disclosed(getter(d)))
        missing[name] = {"missing": n_missing, "of": len(pool), "pct_missing": round(n_missing / max(1, len(pool)) * 100, 1)}
    flags = Counter(f for d in deals for f in d.get("flags") or [])
    review = [
        {"deal_id": d["deal_id"], "title": d.get("title"), "confidence": d.get("confidence"), "flags": d.get("flags")}
        for d in deals
        if d.get("confidence") == "Low" or {"roles_unresolved", "conflicting_role_signals"} & set(d.get("flags") or [])
    ]
    method_counts = Counter()
    for d in deals:
        for part in (d, d.get("target") or {}, d.get("acquirer") or {}, d.get("financials") or {}):
            for v in part.values():
                if isinstance(v, dict) and "method" in v and v.get("value") is not None:
                    method_counts[v["method"]] += 1
    report = {
        "new_deals": sorted(set(d["deal_id"] for d in deals) - previous_ids),
        "new_deal_count": len(set(d["deal_id"] for d in deals) - previous_ids),
        "total_deals": len(deals),
        "evidence_events": evidence_count,
        "duplicates_merged": sum(len(d["sources"]) - 1 for d in multi_source),
        "deals_with_multiple_sources": len(multi_source),
        "missing_fields": missing,
        "flags": dict(flags),
        "confidence": dict(Counter(d.get("confidence") for d in deals)),
        "field_methods": dict(method_counts),
        "flagged_for_review": review[:200],
        "flagged_for_review_count": len(review),
        "source_errors": run_errors[:100],
        "source_error_count": len(run_errors),
        "sources": sources,
    }
    if v1_records is not None and evidence_ids is not None:
        missing_v1 = [sorted(r) for r in v1_records if not (r & evidence_ids)]
        report["v1_migration"] = {
            "v1_records": len(v1_records),
            "covered_in_v2_evidence": len(v1_records) - len(missing_v1),
            "not_covered": missing_v1[:100],
        }
    return report


def summary_line(report: dict) -> str:
    return (f"{report['new_deal_count']} new deals, {report['duplicates_merged']} duplicate filings merged, "
            f"{report['flagged_for_review_count']} records flagged for review, {report['source_error_count']} source errors")
