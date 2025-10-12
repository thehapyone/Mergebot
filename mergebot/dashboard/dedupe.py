from collections.abc import Iterable
from typing import Any


def _is_non_empty_non_na(value: str) -> bool:
    v = (value or "").strip()
    return bool(v) and v.upper() != "N/A"


def stats_quality_key(
    impact_score: str, recommendation: str, last_reviewed: str
) -> tuple[int, int, int]:
    """
    Quality key for dashboard stats when parsing prior rows.
    Order of preference (higher is better):
    1) Has real Last Reviewed (not empty/N/A)
    2) Has Recommendation (non-empty)
    3) Has Impact Score (non-empty and not N/A)
    """
    has_last_reviewed = 1 if _is_non_empty_non_na(last_reviewed) else 0
    has_recommendation = 1 if (recommendation or "").strip() else 0
    has_impact = 1 if _is_non_empty_non_na(impact_score) else 0
    return (has_last_reviewed, has_recommendation, has_impact)


def _status_priority(status: str) -> int:
    """
    Priority for row status when deduping current run results.
    Higher is better.
    """
    if status == "Analyzed":
        return 2
    if status == "Tracked":
        return 1
    return 0  # Error/unknown


def _row_quality_key(row: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """
    Composite quality key for deduping rows emitted to the dashboard.
    Order of preference:
    1) Status priority (Analyzed > Tracked > Error/other)
    2) Has Last Reviewed
    3) Has Recommendation
    4) Has Impact Score
    5) Has a real analysis link
    """
    status = row.get("status", "")
    impact = str(row.get("impact_score") or "")
    recommendation = str(row.get("recommendation") or "")
    last_reviewed = str(row.get("last_reviewed") or "")
    link = str(row.get("analysis_link") or "")

    a, b, c = stats_quality_key(impact, recommendation, last_reviewed)
    has_link = 1 if (link.strip() and link.strip() != "#") else 0
    return (_status_priority(status), a, b, c, has_link)


def dedupe_mr_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate dashboard rows by PR/MR id, keeping the highest-quality row per id.
    """
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = str(r.get("id"))
        cur = best.get(key)
        if cur is None or _row_quality_key(r) > _row_quality_key(cur):
            best[key] = r
    return list(best.values())


def dedupe_prs_by_id(prs: Iterable[Any], pr_id_attr: str) -> list[Any]:
    """
    Return a list of PR/MR objects with unique IDs (stringified) based on pr_id_attr.
    Keeps the first occurrence to preserve input priority.
    """
    seen = set()
    unique: list[Any] = []
    for pr in prs:
        pid = str(getattr(pr, pr_id_attr))
        if pid in seen:
            continue
        seen.add(pid)
        unique.append(pr)
    return unique
