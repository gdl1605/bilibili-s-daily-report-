from __future__ import annotations

import json
import ssl
from collections import Counter
from typing import Any, Callable
from urllib import request

import certifi

from .comparison import build_daily_comparison
from .config import AppConfig
from .models import DailyComparison, DailyInsight, DailyMetrics, ViewingMemory

UrlOpen = Callable[..., Any]


def generate_daily_insight(
    metrics: DailyMetrics,
    metrics_history: list[DailyMetrics],
    *,
    config: AppConfig,
    urlopen: UrlOpen | None = None,
) -> DailyInsight:
    comparison = build_daily_comparison(metrics, metrics_history)
    fallback = build_rule_based_insight(metrics, metrics_history, comparison=comparison)
    if not config.ai_enabled:
        return fallback
    if not config.ai_api_key or not config.ai_model:
        return _with_warning(fallback, "AI insight skipped: missing AI_API_KEY or AI_MODEL")

    try:
        return _request_ai_insight(
            metrics,
            metrics_history,
            comparison=comparison,
            config=config,
            urlopen=urlopen or _default_urlopen,
        )
    except Exception as exc:  # noqa: BLE001 - any AI failure must not block email.
        return _with_warning(fallback, f"AI insight fallback: {type(exc).__name__}")


def build_rule_based_insight(
    metrics: DailyMetrics,
    metrics_history: list[DailyMetrics],
    *,
    comparison: DailyComparison | None = None,
) -> DailyInsight:
    comparison = comparison or build_daily_comparison(metrics, metrics_history)
    payload = build_ai_payload(metrics, metrics_history, comparison=comparison)
    last_7 = payload["trends"]["last_7_days"]
    top_category = _top_name(metrics.top_categories)
    top_author = _top_name(metrics.top_authors)
    summary = (
        f"今天共看了 {max(0, metrics.total_records)} 条，估算观看 {_format_seconds(metrics.estimated_watch_seconds)}，"
        f"平均完成率 {_format_percent(metrics.completion_rate_avg)}。"
    )
    if top_category:
        summary += f"最常看的分区是 {top_category}"
        if top_author:
            summary += f"，Top UP 主是 {top_author}"
        summary += "。"
    if last_7["days"] > 1:
        delta = int(metrics.estimated_watch_seconds - last_7["avg_estimated_watch_seconds"])
        if abs(delta) >= 60:
            direction = "高于" if delta > 0 else "低于"
            summary += f"观看时长{direction}近 7 日均值 {_format_seconds(abs(delta))}。"
    yesterday = comparison.vs_yesterday
    if yesterday.available:
        watch_delta = yesterday.metrics["estimated_watch_seconds"]["delta"]
        if abs(float(watch_delta)) >= 60:
            direction = "增加" if watch_delta > 0 else "减少"
            summary += f"较昨日观看时长{direction}{_format_seconds(abs(float(watch_delta)))}。"

    if metrics.total_records <= 0:
        encouragement = "今天几乎没有观看记录，留白也是一种节奏。"
    elif metrics.high_completion_video_ratio >= 0.35:
        encouragement = "深度观看占比不错，说明今天有内容真正留住了你。"
    elif metrics.quick_exit_video_ratio >= 0.4:
        encouragement = "今天筛选内容比较快，能及时划走不合适的视频也算高效。"
    else:
        encouragement = "观看节奏比较平衡，可以继续保持轻量复盘。"

    if yesterday.available and yesterday.metrics["quick_exit_video_ratio"]["delta_pp"] <= -5:
        reminder = "快速划走较昨日下降，今天选内容更稳定。"
    elif metrics.warnings:
        reminder = "部分视频缺少完整进度，观看时长已按保守规则估算。"
    elif metrics.estimated_watch_seconds >= 7200:
        reminder = "今天观看时间偏长，记得给眼睛和注意力安排休息。"
    elif metrics.quick_exit_video_ratio >= 0.4:
        reminder = "快速划走偏多时，可以先用收藏或稍后再看来减少反复试探。"
    else:
        reminder = "看完后顺手复盘一下分区和 UP 主，明天会更容易选内容。"

    if metrics.quick_exit_video_ratio >= 0.3:
        tomorrow_goal = "明天先挑 3 个最想看的视频，试着降低快速划走比例。"
    elif metrics.short_video_count > metrics.long_video_count:
        tomorrow_goal = "明天安排 1 个稍长的高质量视频，给深度观看留一点空间。"
    else:
        tomorrow_goal = "明天继续保留一个明确主题，让观看更像主动选择。"

    return DailyInsight(
        summary=summary,
        encouragement=encouragement,
        reminder=reminder,
        tomorrow_goal=tomorrow_goal,
        source="rules",
        warnings=list(metrics.warnings),
    )


def build_ai_payload(
    metrics: DailyMetrics,
    metrics_history: list[DailyMetrics],
    *,
    comparison: DailyComparison | None = None,
    viewing_memory: ViewingMemory | None = None,
) -> dict[str, Any]:
    history = _history_with_current(metrics, metrics_history)
    comparison = comparison or build_daily_comparison(metrics, metrics_history)
    payload = {
        "current_day": _metric_snapshot(metrics),
        "trends": {
            "last_7_days": _aggregate_metrics(history[-7:], metrics),
            "last_30_days": _aggregate_metrics(history[-30:], metrics),
        },
        "comparison": comparison.to_dict(),
    }
    if viewing_memory is not None:
        payload["viewer_memory"] = viewing_memory.to_dict()
    return payload


def _request_ai_insight(
    metrics: DailyMetrics,
    metrics_history: list[DailyMetrics],
    *,
    comparison: DailyComparison,
    config: AppConfig,
    urlopen: UrlOpen,
) -> DailyInsight:
    payload = build_ai_payload(metrics, metrics_history, comparison=comparison)
    body = {
        "model": config.ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "只返回紧凑中文 JSON，字段必须是字符串 summary、encouragement、reminder、tomorrow_goal。"
                    "语气温暖、像真人提醒但保持克制。只能使用提供的聚合指标，以及如果提供的 "
                    "viewer_memory；不要假装知道未提供的个人事实。禁止使用或要求视频标题、原始观看明细、"
                    "Cookie、SMTP 凭据、邮箱、完整请求头等敏感或原始数据。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        "temperature": 0.2,
    }
    endpoint = f"{config.ai_base_url.rstrip('/')}/chat/completions"
    req = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.ai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=config.ai_timeout_seconds) as response:
        response_data = json.loads(response.read().decode("utf-8"))
    parsed = _parse_openai_response(response_data)
    return DailyInsight(
        summary=parsed["summary"],
        encouragement=parsed["encouragement"],
        reminder=parsed["reminder"],
        tomorrow_goal=parsed["tomorrow_goal"],
        source="ai",
        warnings=_string_list(parsed.get("warnings")),
    )


def _default_urlopen(req: request.Request, *, timeout: float) -> Any:
    context = ssl.create_default_context(cafile=certifi.where())
    return request.urlopen(req, timeout=timeout, context=context)


def _parse_openai_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("AI response missing content")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("AI response content is not an object")
    required = ("summary", "encouragement", "reminder", "tomorrow_goal")
    if not all(isinstance(parsed.get(field), str) and parsed[field].strip() for field in required):
        raise ValueError("AI response missing required insight fields")
    return {**parsed, **{field: parsed[field].strip() for field in required}}


def _metric_snapshot(metrics: DailyMetrics) -> dict[str, Any]:
    return {
        "date": metrics.date,
        "total_records": max(0, metrics.total_records),
        "unique_videos": max(0, metrics.unique_videos),
        "short_video_count": max(0, metrics.short_video_count),
        "long_video_count": max(0, metrics.long_video_count),
        "estimated_watch_seconds": max(0, metrics.estimated_watch_seconds),
        "total_duration_seconds": max(0, metrics.total_duration_seconds),
        "completion_rate_avg": round(float(metrics.completion_rate_avg), 4),
        "high_completion_video_count": max(0, metrics.high_completion_video_count),
        "high_completion_video_ratio": round(float(metrics.high_completion_video_ratio), 4),
        "quick_exit_video_count": max(0, metrics.quick_exit_video_count),
        "quick_exit_video_ratio": round(float(metrics.quick_exit_video_ratio), 4),
        "top_authors": _top_rows(metrics.top_authors),
        "top_categories": _top_rows(metrics.top_categories),
    }


def _aggregate_metrics(rows: list[DailyMetrics], current: DailyMetrics) -> dict[str, Any]:
    if not rows:
        return {
            "days": 0,
            "total_records": 0,
            "avg_records": 0,
            "total_estimated_watch_seconds": 0,
            "avg_estimated_watch_seconds": 0,
            "avg_completion_rate": 0,
            "avg_high_completion_ratio": 0,
            "avg_quick_exit_ratio": 0,
            "avg_short_video_ratio": 0,
            "current_vs_avg_watch_seconds": 0,
            "top_authors": [],
            "top_categories": [],
        }
    days = len(rows)
    total_records = sum(max(0, row.total_records) for row in rows)
    total_watch = sum(max(0, row.estimated_watch_seconds) for row in rows)
    avg_watch = total_watch / days
    return {
        "days": days,
        "total_records": total_records,
        "avg_records": round(total_records / days, 2),
        "total_estimated_watch_seconds": total_watch,
        "avg_estimated_watch_seconds": round(avg_watch, 2),
        "avg_completion_rate": round(sum(float(row.completion_rate_avg) for row in rows) / days, 4),
        "avg_high_completion_ratio": round(sum(float(row.high_completion_video_ratio) for row in rows) / days, 4),
        "avg_quick_exit_ratio": round(sum(float(row.quick_exit_video_ratio) for row in rows) / days, 4),
        "avg_short_video_ratio": round(
            sum(_safe_ratio(row.short_video_count, row.total_records) for row in rows) / days,
            4,
        ),
        "current_vs_avg_watch_seconds": round(current.estimated_watch_seconds - avg_watch, 2),
        "top_authors": _aggregate_top_rows(rows, "top_authors"),
        "top_categories": _aggregate_top_rows(rows, "top_categories"),
    }


def _history_with_current(metrics: DailyMetrics, metrics_history: list[DailyMetrics]) -> list[DailyMetrics]:
    rows = [row for row in metrics_history if row.date <= metrics.date and row.date != metrics.date]
    rows.append(metrics)
    return sorted(rows, key=lambda row: row.date)


def _aggregate_top_rows(rows: list[DailyMetrics], field: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in getattr(row, field):
            name = str(item.get("name") or "Unknown")
            counter[name] += max(0, int(item.get("count") or 0))
    return [{"name": name, "count": count} for name, count in counter.most_common(3)]


def _top_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows[:3]:
        result.append({"name": str(row.get("name") or "Unknown"), "count": max(0, int(row.get("count") or 0))})
    return result


def _with_warning(insight: DailyInsight, warning: str) -> DailyInsight:
    return DailyInsight(
        summary=insight.summary,
        encouragement=insight.encouragement,
        reminder=insight.reminder,
        tomorrow_goal=insight.tomorrow_goal,
        source="rules",
        warnings=[*insight.warnings, warning],
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _top_name(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    return str(rows[0].get("name") or "")


def _format_seconds(seconds: int | float) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minute}m"
    if minute:
        return f"{minute}m {sec}s"
    return f"{sec}s"


def _format_percent(value: float) -> str:
    return f"{min(1.0, max(0.0, float(value))):.1%}"


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, float(numerator) / float(denominator)))
