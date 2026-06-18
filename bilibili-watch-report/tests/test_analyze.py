from datetime import date

from bili_report.analyze import analyze_day, estimate_watch_seconds, is_short_video
from bili_report.models import EnrichedHistoryItem


def make_item(
    *,
    bvid: str,
    view_at: int,
    title: str = "Video",
    author_name: str = "Author",
    tname: str = "Category",
    duration: int | None = 100,
    progress: int | None = 10,
    raw: dict | None = None,
) -> EnrichedHistoryItem:
    return EnrichedHistoryItem(
        title=title,
        bvid=bvid,
        aid=None,
        author_name=author_name,
        business="archive",
        view_at=view_at,
        progress=progress,
        duration=duration,
        tname=tname,
        raw=raw or {},
    )


def test_estimated_watch_time_clamps_progress_and_uses_conservative_missing_value() -> None:
    assert estimate_watch_seconds(progress=500, duration=300) == 300
    assert estimate_watch_seconds(progress=-1, duration=200) == 30
    assert estimate_watch_seconds(progress=None, duration=20) == 20
    assert estimate_watch_seconds(progress=None, duration=None) == 0


def test_short_video_prefers_explicit_api_signal_then_falls_back_to_three_minutes() -> None:
    explicit_short = make_item(bvid="BVshort", view_at=1, duration=500, raw={"duration_type": "short"})
    fallback_short = make_item(bvid="BVfallback", view_at=2, duration=179, raw={})
    fallback_long = make_item(bvid="BVlong", view_at=3, duration=180, raw={})

    assert is_short_video(explicit_short, short_threshold_seconds=180) is True
    assert is_short_video(fallback_short, short_threshold_seconds=180) is True
    assert is_short_video(fallback_long, short_threshold_seconds=180) is False


def test_analyze_day_dedupes_by_video_and_timestamp_and_builds_top_lists() -> None:
    items = [
        make_item(
            bvid="BV1",
            view_at=100,
            title="Short A",
            author_name="Alice",
            tname="Music",
            duration=100,
            progress=50,
        ),
        make_item(
            bvid="BV1",
            view_at=100,
            title="Duplicate Short A",
            author_name="Alice",
            tname="Music",
            duration=100,
            progress=50,
        ),
        make_item(
            bvid="BV2",
            view_at=200,
            title="Long B",
            author_name="Bob",
            tname="Tech",
            duration=600,
            progress=700,
        ),
        make_item(
            bvid="BV3",
            view_at=300,
            title="Explicit Short C",
            author_name="Alice",
            tname="Tech",
            duration=500,
            progress=-1,
            raw={"duration_type": "short"},
        ),
    ]

    metrics = analyze_day(items, target_date=date(2026, 6, 17))

    assert metrics.total_records == 3
    assert metrics.unique_videos == 3
    assert metrics.short_video_count == 2
    assert metrics.long_video_count == 1
    assert metrics.estimated_watch_seconds == 680
    assert metrics.total_duration_seconds == 1200
    assert metrics.high_completion_video_count == 1
    assert metrics.high_completion_video_ratio == 0.3333
    assert metrics.quick_exit_video_count == 0
    assert metrics.quick_exit_video_ratio == 0.0
    assert metrics.top_authors[0] == {"name": "Alice", "count": 2}
    assert metrics.top_categories[0] == {"name": "Tech", "count": 2}


def test_analyze_day_reports_high_completion_and_quick_exit_ratios() -> None:
    items = [
        make_item(bvid="BVcomplete", view_at=1, duration=100, progress=80),
        make_item(bvid="BValmost", view_at=2, duration=100, progress=79),
        make_item(bvid="BVquick", view_at=3, duration=100, progress=15),
        make_item(bvid="BVunknown", view_at=4, duration=100, progress=-1),
    ]

    metrics = analyze_day(items, target_date=date(2026, 6, 17))

    assert metrics.high_completion_video_count == 1
    assert metrics.high_completion_video_ratio == 0.25
    assert metrics.quick_exit_video_count == 1
    assert metrics.quick_exit_video_ratio == 0.25
