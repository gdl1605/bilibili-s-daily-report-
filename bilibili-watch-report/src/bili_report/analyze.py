from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from .models import DailyMetrics, EnrichedHistoryItem


def estimate_watch_seconds(progress: int | None, duration: int | None) -> int:
    if progress is not None and progress >= 0:
        if duration is not None and duration > 0:
            return max(0, min(progress, duration))
        return max(0, progress)
    if duration is None or duration <= 0:
        return 0
    return min(duration, 30)


def is_short_video(item: EnrichedHistoryItem, *, short_threshold_seconds: int = 180) -> bool:
    explicit = _explicit_short_signal(item.raw)
    if explicit is not None:
        return explicit
    if item.duration is None:
        return False
    return item.duration < short_threshold_seconds


def analyze_day(
    items: list[EnrichedHistoryItem],
    *,
    target_date: date,
    short_threshold_seconds: int = 180,
) -> DailyMetrics:
    deduped = _dedupe(items)
    estimated_watch = 0
    total_duration = 0
    short_count = 0
    long_count = 0
    high_completion_count = 0
    quick_exit_count = 0
    completion_rates: list[float] = []
    conservative_estimates = 0
    category_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "estimated_watch_seconds": 0, "total_duration_seconds": 0}
    )

    for item in deduped:
        watched = estimate_watch_seconds(item.progress, item.duration)
        estimated_watch += watched
        category_name = item.tname or "Unknown"
        category_totals[category_name]["count"] += 1
        category_totals[category_name]["estimated_watch_seconds"] += watched
        if item.duration:
            total_duration += item.duration
            category_totals[category_name]["total_duration_seconds"] += item.duration
            completion_rate = watched / item.duration
            completion_rates.append(completion_rate)
            if completion_rate >= 0.8:
                high_completion_count += 1
        if item.progress is not None and 0 <= item.progress <= 15:
            quick_exit_count += 1
        if item.progress is None or item.progress < 0:
            conservative_estimates += 1
        if is_short_video(item, short_threshold_seconds=short_threshold_seconds):
            short_count += 1
        else:
            long_count += 1

    warnings = []
    if conservative_estimates:
        warnings.append(f"{conservative_estimates} item(s) used conservative watch-time estimate")

    return DailyMetrics(
        date=target_date.isoformat(),
        total_records=len(deduped),
        unique_videos=len({item.stable_video_id for item in deduped}),
        short_video_count=short_count,
        long_video_count=long_count,
        estimated_watch_seconds=int(estimated_watch),
        total_duration_seconds=int(total_duration),
        completion_rate_avg=round(sum(completion_rates) / len(completion_rates), 4) if completion_rates else 0.0,
        high_completion_video_count=high_completion_count,
        high_completion_video_ratio=round(high_completion_count / len(deduped), 4) if deduped else 0.0,
        quick_exit_video_count=quick_exit_count,
        quick_exit_video_ratio=round(quick_exit_count / len(deduped), 4) if deduped else 0.0,
        top_authors=_top_counts(item.author_name or "Unknown" for item in deduped),
        top_categories=_top_counts(item.tname or "Unknown" for item in deduped),
        category_breakdown=_category_breakdown(category_totals),
        warnings=warnings,
    )


def _dedupe(items: list[EnrichedHistoryItem]) -> list[EnrichedHistoryItem]:
    seen: set[str] = set()
    deduped: list[EnrichedHistoryItem] = []
    for item in items:
        key = f"{item.stable_video_id}:{item.view_at}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _top_counts(values: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    counter = Counter(values)
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _category_breakdown(category_totals: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    rows = [
        {
            "name": name,
            "count": values["count"],
            "estimated_watch_seconds": values["estimated_watch_seconds"],
            "total_duration_seconds": values["total_duration_seconds"],
        }
        for name, values in category_totals.items()
    ]
    return sorted(rows, key=lambda row: (-int(row["count"]), str(row["name"])))


def _explicit_short_signal(raw: dict[str, Any]) -> bool | None:
    for container in (raw, raw.get("history") or {}, raw.get("detail") or {}):
        if not isinstance(container, dict):
            continue
        for key in ("is_short", "is_short_video", "short_video"):
            if key in container:
                return bool(container[key])
        value = container.get("duration_type") or container.get("video_type") or container.get("type_name")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"short", "short_video", "short-video", "vertical", "短视频"}:
                return True
            if normalized in {"long", "long_video", "long-video", "archive", "长视频"}:
                return False
    return None
