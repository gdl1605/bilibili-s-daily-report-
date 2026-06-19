from bili_report.comparison import build_daily_comparison
from bili_report.models import DailyMetrics


def make_metrics(
    date: str,
    *,
    records: int = 10,
    watch_seconds: int = 600,
    duration_seconds: int = 1200,
    completion: float = 0.5,
    high_ratio: float = 0.3,
    quick_ratio: float = 0.2,
    short_count: int = 4,
    categories: list[dict] | None = None,
) -> DailyMetrics:
    categories = categories or [
        {"name": "Tech", "count": 6, "estimated_watch_seconds": 360, "total_duration_seconds": 700},
        {"name": "Music", "count": 4, "estimated_watch_seconds": 240, "total_duration_seconds": 500},
    ]
    return DailyMetrics(
        date=date,
        total_records=records,
        unique_videos=records,
        short_video_count=short_count,
        long_video_count=max(0, records - short_count),
        estimated_watch_seconds=watch_seconds,
        total_duration_seconds=duration_seconds,
        completion_rate_avg=completion,
        high_completion_video_count=round(records * high_ratio),
        high_completion_video_ratio=high_ratio,
        quick_exit_video_count=round(records * quick_ratio),
        quick_exit_video_ratio=quick_ratio,
        top_authors=[],
        top_categories=[{"name": row["name"], "count": row["count"]} for row in categories[:5]],
        category_breakdown=categories,
        warnings=[],
    )


def test_build_daily_comparison_compares_yesterday_and_uses_percentage_point_ratio_deltas() -> None:
    current = make_metrics(
        "2026-06-17",
        records=12,
        watch_seconds=900,
        duration_seconds=1800,
        completion=0.6,
        high_ratio=0.5,
        quick_ratio=0.25,
        short_count=6,
    )
    yesterday = make_metrics(
        "2026-06-16",
        records=8,
        watch_seconds=300,
        duration_seconds=1200,
        completion=0.45,
        high_ratio=0.25,
        quick_ratio=0.5,
        short_count=2,
    )

    comparison = build_daily_comparison(current, [yesterday])

    assert comparison.vs_yesterday.available is True
    assert comparison.vs_yesterday.metrics["total_records"]["delta"] == 4
    assert comparison.vs_yesterday.metrics["estimated_watch_seconds"]["delta"] == 600
    assert comparison.vs_yesterday.metrics["watch_ratio"]["current"] == 0.5
    assert comparison.vs_yesterday.metrics["watch_ratio"]["baseline"] == 0.25
    assert comparison.vs_yesterday.metrics["watch_ratio"]["delta_pp"] == 25.0
    assert comparison.vs_yesterday.metrics["quick_exit_video_ratio"]["delta_pp"] == -25.0
    assert comparison.vs_yesterday.metrics["short_video_ratio"]["delta_pp"] == 25.0


def test_build_daily_comparison_marks_missing_yesterday_unavailable_but_calculates_recent_history_warning() -> None:
    current = make_metrics("2026-06-17", watch_seconds=600)
    history = [
        make_metrics("2026-06-15", watch_seconds=300),
        make_metrics("2026-06-10", watch_seconds=900),
    ]

    comparison = build_daily_comparison(current, history)

    assert comparison.vs_yesterday.available is False
    assert comparison.vs_yesterday.warnings == ["缺少昨日数据"]
    assert comparison.vs_recent_7d.available is True
    assert comparison.vs_recent_7d.baseline_days == 2
    assert comparison.vs_recent_7d.metrics["estimated_watch_seconds"]["baseline"] == 600
    assert comparison.vs_recent_7d.metrics["estimated_watch_seconds"]["delta"] == 0
    assert comparison.vs_recent_7d.warnings == ["历史不足：近 7 日少于 3 天数据"]


def test_build_daily_comparison_handles_zero_denominators_and_limits_recent_7d_to_prior_days() -> None:
    current = make_metrics("2026-06-17", watch_seconds=100, duration_seconds=0)
    history = [
        make_metrics(f"2026-06-{day:02d}", watch_seconds=day * 10, duration_seconds=0)
        for day in range(1, 17)
    ]

    comparison = build_daily_comparison(current, history)

    assert comparison.vs_recent_7d.baseline_days == 7
    assert comparison.vs_recent_7d.metrics["watch_ratio"]["current"] == 0.0
    assert comparison.vs_recent_7d.metrics["watch_ratio"]["baseline"] == 0.0
    assert comparison.vs_recent_7d.metrics["watch_ratio"]["delta_pp"] == 0.0
    assert comparison.vs_recent_7d.metrics["estimated_watch_seconds"]["baseline"] == 130


def test_build_daily_comparison_reports_category_new_risen_fallen_and_flat_statuses() -> None:
    current = make_metrics(
        "2026-06-17",
        records=10,
        categories=[
            {"name": "Tech", "count": 5, "estimated_watch_seconds": 300, "total_duration_seconds": 500},
            {"name": "Music", "count": 3, "estimated_watch_seconds": 180, "total_duration_seconds": 300},
            {"name": "Game", "count": 1, "estimated_watch_seconds": 60, "total_duration_seconds": 100},
            {"name": "Dance", "count": 1, "estimated_watch_seconds": 60, "total_duration_seconds": 100},
        ],
    )
    yesterday = make_metrics(
        "2026-06-16",
        records=10,
        categories=[
            {"name": "Tech", "count": 2, "estimated_watch_seconds": 120, "total_duration_seconds": 200},
            {"name": "Music", "count": 5, "estimated_watch_seconds": 300, "total_duration_seconds": 500},
            {"name": "Game", "count": 1, "estimated_watch_seconds": 60, "total_duration_seconds": 100},
            {"name": "Life", "count": 2, "estimated_watch_seconds": 120, "total_duration_seconds": 200},
        ],
    )

    comparison = build_daily_comparison(current, [yesterday])
    statuses = {row["name"]: row for row in comparison.vs_yesterday.category_changes}

    assert statuses["Tech"]["status"] == "risen"
    assert statuses["Tech"]["share_delta_pp"] == 30.0
    assert statuses["Music"]["status"] == "fallen"
    assert statuses["Music"]["count_delta"] == -2
    assert statuses["Game"]["status"] == "flat"
    assert statuses["Dance"]["status"] == "new"
