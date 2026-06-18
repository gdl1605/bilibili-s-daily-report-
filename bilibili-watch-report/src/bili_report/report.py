from __future__ import annotations

import html
import json
import math
import re
from datetime import date
from pathlib import Path

from .models import DailyMetrics, EnrichedHistoryItem

PINK = "#FB7299"
PINK_SOFT = "#fb9ab5"
PINK_PALE = "#ffc2d4"
BLUE = "#00AEEC"
BLUE_SOFT = "#54c7f0"
GRAY_TEXT = "#71717a"
CIRCLE_50 = round(2 * math.pi * 50, 1)
CIRCLE_52 = round(2 * math.pi * 52, 1)


def build_email_html(
    metrics: DailyMetrics,
    entries: list[EnrichedHistoryItem],
    *,
    dashboard_url: str | None = None,
) -> str:
    watch_ratio = _safe_ratio(metrics.estimated_watch_seconds, metrics.total_duration_seconds)
    completion_ratio = _clamp(metrics.completion_rate_avg)
    total_records = max(0, metrics.total_records)
    short_ratio = _safe_ratio(metrics.short_video_count, total_records)
    long_ratio = _safe_ratio(metrics.long_video_count, total_records)
    short_dash = round(CIRCLE_50 * short_ratio, 1)
    long_dash = round(CIRCLE_50 * long_ratio, 1)
    high_count = max(0, metrics.high_completion_video_count)
    quick_count = max(0, metrics.quick_exit_video_count)
    middle_count = max(0, total_records - high_count - quick_count)
    engagement_total = max(1, quick_count + middle_count + high_count)
    unique_caption = (
        "全部为唯一视频"
        if metrics.unique_videos == metrics.total_records
        else f"{metrics.unique_videos} 个唯一视频"
    )
    dashboard_link = (
        f' · <a href="{html.escape(dashboard_url, quote=True)}" '
        f'style="color:#8a6d2f; font-weight:700; text-decoration:none;">打开仪表盘</a>'
        if dashboard_url
        else ""
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>B 站观看日报 - {html.escape(metrics.date)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(14px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes growW {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    @media (max-width: 760px) {{
      .kpi-grid, .bento-grid, .two-col {{ grid-template-columns: 1fr !important; }}
      .report-header {{ align-items: flex-start !important; }}
      .record-total {{ text-align: left !important; }}
      .recent-author {{ display: none !important; }}
    }}
  </style>
</head>
<body style="margin:0; background:#f4f4f6;">
  <div data-report-date="{html.escape(metrics.date)}" style="min-height:100vh; background:#f4f4f6; font-family:'Plus Jakarta Sans','PingFang SC','Microsoft YaHei',system-ui,sans-serif; color:#18181b; padding:40px 24px 64px;">
    <div style="max-width:1080px; margin:0 auto;">
      <header class="report-header" style="display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:20px; padding-bottom:24px; border-bottom:1px solid #e4e4e9; margin-bottom:28px; animation:fadeUp .5s ease both;">
        <div>
          <div style="display:flex; align-items:center; gap:9px; margin-bottom:12px;">
            <span style="display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; background:{PINK}; border-radius:7px; color:#fff;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m7 2 3 4M17 2l-3 4"/><rect x="3" y="6" width="18" height="14" rx="3"/><path d="M8 12v3M16 12v3"/></svg>
            </span>
            <span style="font-size:12px; font-weight:700; letter-spacing:.16em; color:{PINK}; text-transform:uppercase;">Bilibili · 每日观看洞察</span>
          </div>
          <h1 style="margin:0; font-size:38px; font-weight:800; letter-spacing:0; line-height:1.05;">{html.escape(_format_chinese_date(metrics.date))}</h1>
          <p style="margin:8px 0 0; color:{GRAY_TEXT}; font-size:14px;">{html.escape(_weekday_zh(metrics.date))} · 全天观看行为汇总</p>
        </div>
        <div class="record-total" style="text-align:right;">
          <div style="font-family:'Space Grotesk',sans-serif; font-size:54px; font-weight:700; line-height:1; color:#18181b;">{total_records}</div>
          <div style="color:{GRAY_TEXT}; font-size:13px; font-weight:600; margin-top:4px;">条观看记录 · {html.escape(unique_caption)}</div>
        </div>
      </header>

      <section class="kpi-grid" style="display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:14px; animation:fadeUp .5s ease .05s both;">
        {_render_kpi_card("估算观看时长", _format_duration_metric(metrics.estimated_watch_seconds), f"可看时长共 {_format_seconds(metrics.total_duration_seconds)}")}
        {_render_kpi_card("平均完成率", _format_percent_metric(completion_ratio), "单视频平均看完比例")}
        {_render_kpi_card("深度观看", str(high_count), f"看完 80%+ · 占 {_format_percent(metrics.high_completion_video_ratio)}", value_color=PINK)}
        {_render_kpi_card("快速划走", str(quick_count), f"15s 内退出 · 占 {_format_percent(metrics.quick_exit_video_ratio)}", value_color="#8a93a3")}
      </section>

      <section class="bento-grid" style="display:grid; grid-template-columns:1.15fr 1fr 1fr; gap:14px; margin-bottom:14px; animation:fadeUp .5s ease .1s both;">
        <article style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:20px;">
          <div style="font-size:14px; font-weight:700; margin-bottom:2px;">短视频 vs 长视频</div>
          <div style="font-size:12px; color:#a1a1aa; margin-bottom:14px;">按时长划分的视频构成</div>
          <div style="display:flex; align-items:center; gap:18px; flex-wrap:wrap;">
            <div style="position:relative; flex:none;">
              <svg width="124" height="124" viewBox="0 0 124 124" role="img" aria-label="短视频与长视频占比">
                <circle cx="62" cy="62" r="50" fill="none" stroke="#f0f0f3" stroke-width="16"/>
                <circle cx="62" cy="62" r="50" fill="none" stroke="{PINK}" stroke-width="16" stroke-dasharray="{short_dash} {max(0, CIRCLE_50 - short_dash):.1f}" transform="rotate(-90 62 62)"/>
                <circle cx="62" cy="62" r="50" fill="none" stroke="{BLUE}" stroke-width="16" stroke-dasharray="{long_dash} {max(0, CIRCLE_50 - long_dash):.1f}" stroke-dashoffset="-{short_dash}" transform="rotate(-90 62 62)"/>
              </svg>
              <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                <div style="font-family:'Space Grotesk',sans-serif; font-size:26px; font-weight:700; line-height:1;">{total_records}</div>
                <div style="font-size:10.5px; color:#a1a1aa;">视频总数</div>
              </div>
            </div>
            <div style="flex:1; min-width:150px; display:flex; flex-direction:column; gap:12px;">
              {_render_donut_legend("短视频", metrics.short_video_count, short_ratio, PINK)}
              {_render_donut_legend("长视频", metrics.long_video_count, long_ratio, BLUE)}
            </div>
          </div>
        </article>

        {_render_gauge_card("观看时长占比", "实际观看 / 可看总时长", watch_ratio, PINK, _format_seconds(metrics.estimated_watch_seconds))}
        {_render_gauge_card("平均完成率", "每个视频平均看完比例", completion_ratio, BLUE, "完成率")}
      </section>

      <section style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:22px; margin-bottom:14px; animation:fadeUp .5s ease .15s both;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:16px;">
          <div>
            <div style="font-size:14px; font-weight:700;">观看行为分布</div>
            <div style="font-size:12px; color:#a1a1aa; margin-top:2px;">{total_records} 个视频按投入程度划分</div>
          </div>
        </div>
        <div style="display:flex; height:42px; border-radius:10px; overflow:hidden; gap:3px;">
          {_render_distribution_segment(quick_count, quick_count / engagement_total, "#c3cad6", "#fff")}
          {_render_distribution_segment(middle_count, middle_count / engagement_total, PINK_PALE, "#b13a64")}
          {_render_distribution_segment(high_count, high_count / engagement_total, PINK, "#fff")}
        </div>
        <div style="display:flex; gap:28px; margin-top:14px; flex-wrap:wrap;">
          {_render_distribution_legend("15s 内退出", quick_count, _safe_ratio(quick_count, total_records), "#c3cad6")}
          {_render_distribution_legend("中等观看", middle_count, _safe_ratio(middle_count, total_records), PINK_PALE)}
          {_render_distribution_legend("深度观看 80%+", high_count, _safe_ratio(high_count, total_records), PINK)}
        </div>
      </section>

      <section class="two-col" style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px; animation:fadeUp .5s ease .2s both;">
        <article style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:22px;">
          <div style="font-size:14px; font-weight:700; margin-bottom:18px;">Top UP 主</div>
          {_render_rank_bars(metrics.top_authors, PINK, PINK_SOFT)}
        </article>
        <article style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:22px;">
          <div style="font-size:14px; font-weight:700; margin-bottom:18px;">Top 分区</div>
          {_render_rank_bars(metrics.top_categories, BLUE, BLUE_SOFT)}
        </article>
      </section>

      <section style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:22px; margin-bottom:14px; animation:fadeUp .5s ease .25s both;">
        <div style="font-size:14px; font-weight:700; margin-bottom:4px;">最近观看</div>
        <div style="font-size:12px; color:#a1a1aa; margin-bottom:8px;">当日最新的 10 条记录</div>
        <div>{_render_recent_entries(entries)}</div>
      </section>

      <footer style="display:flex; align-items:center; gap:10px; padding:14px 16px; background:#fff7e8; border:1px solid #fce8c4; border-radius:12px; animation:fadeUp .5s ease .3s both;">
        <span style="display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; background:#f5a623; border-radius:50%; color:#fff; flex:none;">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 8v5M12 16.5h.01"/></svg>
        </span>
        <span style="font-size:12.5px; color:#8a6d2f;">{html.escape(_estimate_notice(metrics.warnings))} · 观看占比 = 估算观看时长 / 所有观看视频时长，完成率类指标按去重视频数计算{dashboard_link}</span>
      </footer>
    </div>
  </div>
</body>
</html>"""


def render_dashboard(
    *,
    output_dir: Path,
    metrics_history: list[DailyMetrics],
    recent_entries: dict[str, list[EnrichedHistoryItem]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = sorted(metrics_history, key=lambda item: item.date)[-30:]
    data = {
        "metrics": [metric.to_dict() for metric in metrics],
        "recent_entries": {
            day: [entry.to_dict() for entry in entries[:20]]
            for day, entries in sorted(recent_entries.items())
        },
    }
    (output_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(_dashboard_html(), encoding="utf-8")


def _render_kpi_card(
    label: str,
    value_html: str,
    subtitle: str,
    *,
    value_color: str = "#18181b",
) -> str:
    return f"""<article style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:18px 18px 16px;">
          <div style="font-size:12.5px; color:{GRAY_TEXT}; font-weight:600;">{html.escape(label)}</div>
          <div style="font-family:'Space Grotesk',sans-serif; font-size:32px; font-weight:700; margin-top:8px; line-height:1; color:{value_color};">{value_html}</div>
          <div style="font-size:12px; color:#a1a1aa; margin-top:8px;">{html.escape(subtitle)}</div>
        </article>"""


def _render_donut_legend(label: str, count: int, ratio: float, color: str) -> str:
    return f"""<div>
                <div style="display:flex; align-items:center; gap:7px;"><span style="width:9px; height:9px; border-radius:3px; background:{color};"></span><span style="font-size:12.5px; color:#52525b; font-weight:600;">{html.escape(label)}</span></div>
                <div style="display:flex; align-items:baseline; gap:6px; margin-top:3px; padding-left:16px;"><span style="font-family:'Space Grotesk',sans-serif; font-size:22px; font-weight:700;">{max(0, int(count))}</span><span style="font-size:12px; color:#a1a1aa;">{_format_percent(ratio)}</span></div>
              </div>"""


def _render_gauge_card(title: str, subtitle: str, ratio: float, color: str, footnote: str) -> str:
    offset = round(CIRCLE_52 * (1 - _clamp(ratio)), 1)
    return f"""<article style="background:#fff; border:1px solid #ececf0; border-radius:16px; padding:20px; display:flex; flex-direction:column;">
          <div style="font-size:14px; font-weight:700; margin-bottom:2px;">{html.escape(title)}</div>
          <div style="font-size:12px; color:#a1a1aa; margin-bottom:6px;">{html.escape(subtitle)}</div>
          <div style="position:relative; align-self:center; margin-top:6px;">
            <svg width="132" height="132" viewBox="0 0 132 132" role="img" aria-label="{html.escape(title)} {_format_percent(ratio)}">
              <circle cx="66" cy="66" r="52" fill="none" stroke="#f0f0f3" stroke-width="13"/>
              <circle cx="66" cy="66" r="52" fill="none" stroke="{color}" stroke-width="13" stroke-linecap="round" stroke-dasharray="{CIRCLE_52}" stroke-dashoffset="{offset}" transform="rotate(-90 66 66)"/>
            </svg>
            <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;">
              <div style="font-family:'Space Grotesk',sans-serif; font-size:30px; font-weight:700; line-height:1; color:{color};">{_format_percent(ratio)}</div>
              <div style="font-size:11px; color:#a1a1aa; margin-top:3px;">{html.escape(footnote)}</div>
            </div>
          </div>
        </article>"""


def _render_distribution_segment(count: int, ratio: float, background: str, color: str) -> str:
    label = str(max(0, int(count))) if count > 0 else ""
    return (
        f'<div style="width:{_style_width(ratio)}; background:{background}; display:flex; align-items:center; '
        f'justify-content:center; color:{color}; font-size:12.5px; font-weight:700;">{label}</div>'
    )


def _render_distribution_legend(label: str, count: int, ratio: float, color: str) -> str:
    return (
        f'<div style="display:flex; align-items:center; gap:8px;"><span style="width:10px; height:10px; '
        f'border-radius:3px; background:{color};"></span><span style="font-size:12.5px; color:#52525b;">'
        f'<b>{html.escape(label)}</b> · {max(0, int(count))} ({_format_percent(ratio)})</span></div>'
    )


def _render_rank_bars(rows: list[dict], color: str, soft_color: str) -> str:
    if not rows:
        return '<p style="margin:0; color:#a1a1aa; font-size:13px;">暂无数据。</p>'
    max_count = max(1, *(int(row.get("count") or 0) for row in rows))
    items = []
    for index, row in enumerate(rows[:5]):
        name = html.escape(str(row.get("name") or "Unknown"))
        count = max(0, int(row.get("count") or 0))
        width = _style_width(count / max_count)
        bar_color = color if index < 2 else soft_color
        delay = index * 0.05
        items.append(
            f"""<div>
            <div style="display:flex; justify-content:space-between; gap:12px; font-size:13px; margin-bottom:6px;"><span style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{name}</span><span style="font-family:'Space Grotesk',sans-serif; font-weight:700; color:{GRAY_TEXT};">{count}</span></div>
            <div style="height:9px; background:#f0f0f3; border-radius:999px; overflow:hidden;"><span style="display:block; height:100%; width:{width}; background:{bar_color}; border-radius:999px; transform-origin:left; animation:growW .8s cubic-bezier(.4,0,.2,1) {delay:.2f}s both;"></span></div>
          </div>"""
        )
    return f'<div style="display:flex; flex-direction:column; gap:15px;">{"".join(items)}</div>'


def _render_recent_entries(entries: list[EnrichedHistoryItem]) -> str:
    recent = sorted(entries, key=lambda item: item.view_at, reverse=True)[:10]
    if not recent:
        return '<p style="margin:0; color:#a1a1aa; font-size:13px;">暂无观看记录。</p>'
    rows = []
    for index, item in enumerate(recent, start=1):
        title = html.escape(item.title or "Untitled")
        author = html.escape(item.author_name or "Unknown")
        border = "border-bottom:1px solid #f2f2f4;" if index < len(recent) else ""
        rows.append(
            f"""<div style="display:flex; gap:14px; align-items:center; padding:11px 0; {border}">
            <span style="font-family:'Space Grotesk',sans-serif; font-size:13px; font-weight:700; color:{PINK_SOFT}; width:22px; flex:none;">{index:02d}</span>
            <span style="font-size:13.5px; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{title}</span>
            <span class="recent-author" style="font-size:12px; color:#a1a1aa; flex:none; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{author}</span>
          </div>"""
        )
    return "".join(rows)


def _render_rank_list(rows: list[dict]) -> str:
    if not rows:
        return "<p>暂无数据。</p>"
    items = "".join(f"<li>{html.escape(str(row['name']))}: {int(row['count'])}</li>" for row in rows)
    return f"<ol>{items}</ol>"


def _format_seconds(seconds: int) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minute}m"
    if minute:
        return f"{minute}m {sec}s"
    return f"{sec}s"


def _format_ratio(metrics: DailyMetrics) -> str:
    if metrics.total_duration_seconds <= 0:
        return "0.0%"
    return _format_percent(metrics.estimated_watch_seconds / metrics.total_duration_seconds)


def _format_percent(value: float) -> str:
    return f"{_clamp(value):.1%}"


def _format_duration_metric(seconds: int) -> str:
    minutes, sec = divmod(max(0, int(seconds)), 60)
    hours, minute = divmod(minutes, 60)
    unit_style = 'font-size:18px; color:#a1a1aa;'
    if hours:
        return f'{hours}<span style="{unit_style}">h</span> {minute}<span style="{unit_style}">m</span>'
    if minute:
        return f'{minute}<span style="{unit_style}">m</span> {sec}<span style="{unit_style}">s</span>'
    return f'{sec}<span style="{unit_style}">s</span>'


def _format_percent_metric(value: float) -> str:
    return f'{_clamp(value) * 100:.1f}<span style="font-size:18px; color:#a1a1aa;">%</span>'


def _format_chinese_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


def _weekday_zh(value: str) -> str:
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return "日期未知"
    return weekdays[parsed.weekday()]


def _estimate_notice(warnings: list[str]) -> str:
    for warning in warnings:
        match = re.search(r"(\d+)", warning)
        if match:
            return f"{match.group(1)} 个视频使用了保守的观看时长估算"
    return "观看时长均按接口 progress 字段估算"


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp(float(numerator) / float(denominator))


def _style_width(ratio: float) -> str:
    percentage = _clamp(ratio) * 100
    if 0 < percentage < 3:
        percentage = 3
    return f"{percentage:.1f}%"


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bilibili Watch Report</title>
  <style>
    :root { color-scheme: light; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f8fb; color: #16202a; }
    main { max-width: 1040px; margin: 0 auto; padding: 32px 20px; }
    h1 { margin: 0 0 8px; font-size: 30px; }
    .subtitle { margin: 0 0 24px; color: #5f6f7e; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
    .card, table { background: #fff; border: 1px solid #dce4ec; border-radius: 8px; }
    .card { padding: 16px; }
    .label { color: #607282; font-size: 13px; }
    .value { font-size: 26px; font-weight: 750; margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #edf1f5; }
    th { color: #607282; font-size: 13px; background: #fbfcfe; }
    .bar { height: 10px; background: #dce4ec; border-radius: 999px; overflow: hidden; }
    .bar > span { display: block; height: 100%; background: #157f8f; }
  </style>
</head>
<body>
<main>
  <h1>Bilibili Watch Report</h1>
  <p class="subtitle">Private daily watch-history dashboard generated from your saved metrics.</p>
  <section class="cards" id="cards"></section>
  <h2>Last 30 Days</h2>
  <table>
    <thead><tr><th>Date</th><th>Records</th><th>Short</th><th>Long</th><th>Estimated Watch</th><th>Watch Ratio</th><th>80%+ Watched</th><th>15s Exit</th></tr></thead>
    <tbody id="metrics"></tbody>
  </table>
</main>
<script>
function fmt(seconds) {
  seconds = Math.max(0, Number(seconds || 0));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}
function ratio(row) {
  const total = Number(row.total_duration_seconds || 0);
  if (!total) return '0.0%';
  return `${((Number(row.estimated_watch_seconds || 0) / total) * 100).toFixed(1)}%`;
}
function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}
fetch('data.json')
  .then((response) => response.json())
  .then((data) => {
    const metrics = data.metrics || [];
    const latest = metrics[metrics.length - 1] || {};
    const cards = [
      ['Latest Date', latest.date || '-'],
      ['Records', latest.total_records || 0],
      ['Estimated Watch', fmt(latest.estimated_watch_seconds)],
      ['Watch Ratio', ratio(latest)],
      ['80%+ Watched', pct(latest.high_completion_video_ratio)],
      ['15s Exit', pct(latest.quick_exit_video_ratio)]
    ];
    document.getElementById('cards').innerHTML = cards.map(([label, value]) =>
      `<article class="card"><div class="label">${label}</div><div class="value">${value}</div></article>`
    ).join('');
    document.getElementById('metrics').innerHTML = metrics.map((row) =>
      `<tr><td>${row.date}</td><td>${row.total_records}</td><td>${row.short_video_count}</td><td>${row.long_video_count}</td><td>${fmt(row.estimated_watch_seconds)}</td><td>${ratio(row)}</td><td>${pct(row.high_completion_video_ratio)}</td><td>${pct(row.quick_exit_video_ratio)}</td></tr>`
    ).join('');
  });
</script>
</body>
</html>"""
