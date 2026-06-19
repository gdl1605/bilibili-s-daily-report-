from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DailyInsight:
    summary: str
    encouragement: str
    reminder: str
    tomorrow_goal: str
    source: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DailyInsight":
        return cls(
            summary=str(data.get("summary") or ""),
            encouragement=str(data.get("encouragement") or ""),
            reminder=str(data.get("reminder") or ""),
            tomorrow_goal=str(data.get("tomorrow_goal") or ""),
            source=str(data.get("source") or "rules"),
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnrichedHistoryItem:
    title: str
    bvid: str | None
    aid: int | None
    author_name: str
    business: str
    view_at: int
    progress: int | None
    duration: int | None
    tname: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(
        cls,
        history_item: dict[str, Any],
        video_detail: dict[str, Any] | None = None,
    ) -> "EnrichedHistoryItem":
        detail = video_detail or {}
        history = history_item.get("history") or {}
        owner = detail.get("owner") or {}
        raw = dict(history_item)
        if detail:
            raw["detail"] = detail

        aid = detail.get("aid") or history_item.get("aid")
        if aid is None and (history.get("business") or history_item.get("business")) == "archive":
            aid = history.get("oid")

        return cls(
            title=str(detail.get("title") or history_item.get("title") or history_item.get("long_title") or ""),
            bvid=detail.get("bvid") or history.get("bvid") or history_item.get("bvid"),
            aid=_optional_int(aid),
            author_name=str(owner.get("name") or history_item.get("author_name") or history_item.get("author") or ""),
            business=str(history.get("business") or history_item.get("business") or ""),
            view_at=int(history_item.get("view_at") or 0),
            progress=_optional_int(history_item.get("progress")),
            duration=_optional_int(detail.get("duration") or history_item.get("duration")),
            tname=str(detail.get("tname") or history_item.get("tname") or history_item.get("tag_name") or ""),
            raw=raw,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnrichedHistoryItem":
        return cls(
            title=str(data.get("title") or ""),
            bvid=data.get("bvid"),
            aid=_optional_int(data.get("aid")),
            author_name=str(data.get("author_name") or ""),
            business=str(data.get("business") or ""),
            view_at=int(data.get("view_at") or 0),
            progress=_optional_int(data.get("progress")),
            duration=_optional_int(data.get("duration")),
            tname=str(data.get("tname") or ""),
            raw=dict(data.get("raw") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def stable_video_id(self) -> str:
        if self.bvid:
            return self.bvid
        if self.aid is not None:
            return f"aid:{self.aid}"
        return f"title:{self.title}"


@dataclass(slots=True)
class DailyMetrics:
    date: str
    total_records: int
    unique_videos: int
    short_video_count: int
    long_video_count: int
    estimated_watch_seconds: int
    total_duration_seconds: int
    completion_rate_avg: float
    high_completion_video_count: int
    high_completion_video_ratio: float
    quick_exit_video_count: int
    quick_exit_video_ratio: float
    top_authors: list[dict[str, Any]]
    top_categories: list[dict[str, Any]]
    category_breakdown: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DailyMetrics":
        return cls(
            date=str(data["date"]),
            total_records=int(data.get("total_records") or 0),
            unique_videos=int(data.get("unique_videos") or 0),
            short_video_count=int(data.get("short_video_count") or 0),
            long_video_count=int(data.get("long_video_count") or 0),
            estimated_watch_seconds=int(data.get("estimated_watch_seconds") or 0),
            total_duration_seconds=int(data.get("total_duration_seconds") or 0),
            completion_rate_avg=float(data.get("completion_rate_avg") or 0.0),
            high_completion_video_count=int(data.get("high_completion_video_count") or 0),
            high_completion_video_ratio=float(data.get("high_completion_video_ratio") or 0.0),
            quick_exit_video_count=int(data.get("quick_exit_video_count") or 0),
            quick_exit_video_ratio=float(data.get("quick_exit_video_ratio") or 0.0),
            top_authors=list(data.get("top_authors") or []),
            top_categories=list(data.get("top_categories") or []),
            category_breakdown=list(data.get("category_breakdown") or []),
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ComparisonWindow:
    label: str
    available: bool
    baseline_days: int
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    category_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComparisonWindow":
        return cls(
            label=str(data.get("label") or ""),
            available=bool(data.get("available")),
            baseline_days=int(data.get("baseline_days") or 0),
            metrics=dict(data.get("metrics") or {}),
            category_changes=list(data.get("category_changes") or []),
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DailyComparison:
    date: str
    vs_yesterday: ComparisonWindow
    vs_recent_7d: ComparisonWindow

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DailyComparison":
        return cls(
            date=str(data.get("date") or ""),
            vs_yesterday=ComparisonWindow.from_dict(dict(data.get("vs_yesterday") or {})),
            vs_recent_7d=ComparisonWindow.from_dict(dict(data.get("vs_recent_7d") or {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
