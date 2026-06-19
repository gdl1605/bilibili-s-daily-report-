from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .models import ComparisonWindow, DailyComparison, DailyMetrics

RATIO_METRICS = {
    "watch_ratio",
    "completion_rate_avg",
    "high_completion_video_ratio",
    "quick_exit_video_ratio",
    "short_video_ratio",
}


def build_daily_comparison(current: DailyMetrics, metrics_history: list[DailyMetrics]) -> DailyComparison:
    prior_rows = sorted(
        [row for row in metrics_history if row.date < current.date],
        key=lambda row: row.date,
    )
    yesterday = _find_yesterday(current, prior_rows)
    recent_rows = prior_rows[-7:]

    return DailyComparison(
        date=current.date,
        vs_yesterday=_build_window("较昨日", current, [yesterday] if yesterday else []),
        vs_recent_7d=_build_window("较近 7 日", current, recent_rows),
    )


def _find_yesterday(current: DailyMetrics, prior_rows: list[DailyMetrics]) -> DailyMetrics | None:
    try:
        yesterday = (date.fromisoformat(current.date) - timedelta(days=1)).isoformat()
    except ValueError:
        return None
    for row in reversed(prior_rows):
        if row.date == yesterday:
            return row
    return None


def _build_window(label: str, current: DailyMetrics, baseline_rows: list[DailyMetrics]) -> ComparisonWindow:
    if not baseline_rows:
        return ComparisonWindow(
            label=label,
            available=False,
            baseline_days=0,
            warnings=["缺少昨日数据"] if label == "较昨日" else ["缺少近 7 日历史数据"],
        )

    warnings = []
    if label == "较近 7 日" and len(baseline_rows) < 3:
        warnings.append("历史不足：近 7 日少于 3 天数据")

    return ComparisonWindow(
        label=label,
        available=True,
        baseline_days=len(baseline_rows),
        metrics=_metric_changes(current, baseline_rows),
        category_changes=_category_changes(current, baseline_rows),
        warnings=warnings,
    )


def _metric_changes(current: DailyMetrics, baseline_rows: list[DailyMetrics]) -> dict[str, dict[str, Any]]:
    current_values = _metric_values(current)
    baseline_values = _baseline_metric_values(baseline_rows)
    result: dict[str, dict[str, Any]] = {}
    for key, current_value in current_values.items():
        baseline_value = baseline_values[key]
        row = {
            "current": _round_value(current_value),
            "baseline": _round_value(baseline_value),
        }
        if key in RATIO_METRICS:
            row["delta_pp"] = round((current_value - baseline_value) * 100, 1)
        else:
            row["delta"] = _round_value(current_value - baseline_value)
        result[key] = row
    return result


def _metric_values(metrics: DailyMetrics) -> dict[str, float]:
    return {
        "total_records": float(max(0, metrics.total_records)),
        "estimated_watch_seconds": float(max(0, metrics.estimated_watch_seconds)),
        "watch_ratio": _safe_ratio(metrics.estimated_watch_seconds, metrics.total_duration_seconds),
        "completion_rate_avg": max(0.0, float(metrics.completion_rate_avg)),
        "high_completion_video_ratio": max(0.0, float(metrics.high_completion_video_ratio)),
        "quick_exit_video_ratio": max(0.0, float(metrics.quick_exit_video_ratio)),
        "short_video_ratio": _safe_ratio(metrics.short_video_count, metrics.total_records),
    }


def _baseline_metric_values(rows: list[DailyMetrics]) -> dict[str, float]:
    days = max(1, len(rows))
    total_duration = sum(max(0, row.total_duration_seconds) for row in rows)
    total_watch = sum(max(0, row.estimated_watch_seconds) for row in rows)
    total_records = sum(max(0, row.total_records) for row in rows)
    total_short = sum(max(0, row.short_video_count) for row in rows)
    return {
        "total_records": total_records / days,
        "estimated_watch_seconds": total_watch / days,
        "watch_ratio": _safe_ratio(total_watch, total_duration),
        "completion_rate_avg": sum(max(0.0, float(row.completion_rate_avg)) for row in rows) / days,
        "high_completion_video_ratio": sum(max(0.0, float(row.high_completion_video_ratio)) for row in rows) / days,
        "quick_exit_video_ratio": sum(max(0.0, float(row.quick_exit_video_ratio)) for row in rows) / days,
        "short_video_ratio": _safe_ratio(total_short, total_records),
    }


def _category_changes(current: DailyMetrics, baseline_rows: list[DailyMetrics]) -> list[dict[str, Any]]:
    current_rows = _category_rows(current)
    baseline_totals = _aggregate_category_counts(baseline_rows)
    baseline_total_count = sum(baseline_totals.values())
    baseline_days = max(1, len(baseline_rows))
    current_total_count = sum(max(0, int(row.get("count") or 0)) for row in current_rows)

    changes = []
    for row in current_rows[:5]:
        name = str(row.get("name") or "Unknown")
        current_count = max(0, int(row.get("count") or 0))
        baseline_count_total = baseline_totals.get(name, 0)
        baseline_count = baseline_count_total / baseline_days
        current_share = _safe_ratio(current_count, current_total_count or current.total_records)
        baseline_share = _safe_ratio(baseline_count_total, baseline_total_count)
        share_delta_pp = round((current_share - baseline_share) * 100, 1)
        changes.append(
            {
                "name": name,
                "current_count": current_count,
                "baseline_count": _round_value(baseline_count),
                "current_share": round(current_share, 4),
                "baseline_share": round(baseline_share, 4),
                "share_delta_pp": share_delta_pp,
                "count_delta": _round_value(current_count - baseline_count),
                "status": _category_status(current_count, baseline_count_total, share_delta_pp),
            }
        )
    return changes


def _category_rows(metrics: DailyMetrics) -> list[dict[str, Any]]:
    rows = metrics.category_breakdown or metrics.top_categories
    return sorted(rows, key=lambda row: (-int(row.get("count") or 0), str(row.get("name") or "Unknown")))


def _aggregate_category_counts(rows: list[DailyMetrics]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for metrics in rows:
        for row in _category_rows(metrics):
            name = str(row.get("name") or "Unknown")
            totals[name] = totals.get(name, 0) + max(0, int(row.get("count") or 0))
    return totals


def _category_status(current_count: int, baseline_count_total: int, share_delta_pp: float) -> str:
    if current_count > 0 and baseline_count_total <= 0:
        return "new"
    if share_delta_pp > 1.0:
        return "risen"
    if share_delta_pp < -1.0:
        return "fallen"
    return "flat"


def _round_value(value: float) -> int | float:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, float(numerator) / float(denominator))
