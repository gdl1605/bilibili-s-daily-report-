from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .analyze import analyze_day
from .client import BiliClient
from .config import AppConfig
from .emailer import EmailAttachment, SmtpConfig, send_daily_email
from .models import DailyMetrics, EnrichedHistoryItem
from .report import build_email_html, render_dashboard

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FixtureTransport:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.history_pages = _read_json(fixture_dir / "history_pages.json")
        self.video_details = _read_json(fixture_dir / "video_details.json")
        self.history_index = 0

    def __call__(self, url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if "history/cursor" in url:
            if self.history_index >= len(self.history_pages):
                return {"code": 0, "data": {"list": []}}
            page = self.history_pages[self.history_index]
            self.history_index += 1
            return page
        if "web-interface/view" in url:
            key = params.get("bvid") or str(params.get("aid"))
            return self.video_details[key]
        raise ValueError(f"Unexpected fixture URL: {url}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch-day":
            _fetch_day(args)
        elif args.command == "build-report":
            _build_report(args)
        elif args.command == "send-email":
            _send_email(args)
        elif args.command == "run-daily":
            _run_daily(args)
        else:
            parser.print_help()
            return 1
    except Exception as exc:  # noqa: BLE001 - CLI should return a clear failure.
        print(f"bili-report failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bili-report")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("fetch-day", "build-report", "send-email", "run-daily"):
        command = subparsers.add_parser(name)
        command.add_argument("--date", default=None, help="Target date in YYYY-MM-DD; defaults to yesterday in Asia/Shanghai.")
        command.add_argument("--output-dir", default=".", help="Project output directory.")
        command.add_argument("--fixtures", default=None, help="Fixture directory for offline testing.")
        command.add_argument("--dotenv", default=".env", help="Path to local dotenv file.")

    parser.set_defaults(command=None)
    subparsers.choices["send-email"].add_argument("--dashboard-url", default=None)
    subparsers.choices["run-daily"].add_argument("--skip-email", action="store_true")
    subparsers.choices["run-daily"].add_argument("--dashboard-url", default=None)
    subparsers.choices["build-report"].add_argument("--dashboard-url", default=None)
    return parser


def _fetch_day(args: argparse.Namespace) -> None:
    target_date = _target_date(args.date)
    output_dir = Path(args.output_dir)
    raw, enriched = _fetch_and_enrich(target_date, fixture_dir=_fixture_path(args), dotenv_path=args.dotenv)
    _write_json(_raw_path(output_dir, target_date), raw)
    _write_json(_enriched_path(output_dir, target_date), [item.to_dict() for item in enriched])


def _build_report(args: argparse.Namespace) -> None:
    target_date = _target_date(args.date)
    output_dir = Path(args.output_dir)
    entries = _load_entries_for_report(output_dir, target_date, fixture_dir=_fixture_path(args))
    _write_json(_enriched_path(output_dir, target_date), [entry.to_dict() for entry in entries])
    metrics = analyze_day(entries, target_date=target_date)
    _upsert_metrics(output_dir, metrics)
    _render_site(output_dir, target_date, metrics, entries)
    html = build_email_html(metrics, entries, dashboard_url=args.dashboard_url)
    _report_path(output_dir, target_date).write_text(html, encoding="utf-8")


def _send_email(args: argparse.Namespace) -> None:
    target_date = _target_date(args.date)
    output_dir = Path(args.output_dir)
    config = AppConfig.from_env(dotenv_path=args.dotenv, require_email=True)
    entries = _read_enriched(_enriched_path(output_dir, target_date))
    metrics = _metrics_for_date(output_dir, target_date) or analyze_day(entries, target_date=target_date)
    html = build_email_html(metrics, entries, dashboard_url=args.dashboard_url)
    _send(config, metrics, html)


def _run_daily(args: argparse.Namespace) -> None:
    target_date = _target_date(args.date)
    output_dir = Path(args.output_dir)
    raw, entries = _fetch_and_enrich(target_date, fixture_dir=_fixture_path(args), dotenv_path=args.dotenv)
    _write_json(_raw_path(output_dir, target_date), raw)
    _write_json(_enriched_path(output_dir, target_date), [entry.to_dict() for entry in entries])
    metrics = analyze_day(entries, target_date=target_date)
    _upsert_metrics(output_dir, metrics)
    _render_site(output_dir, target_date, metrics, entries)
    dashboard_url = args.dashboard_url or os.environ.get("GITHUB_PAGES_URL")
    html = build_email_html(metrics, entries, dashboard_url=dashboard_url)
    _report_path(output_dir, target_date).write_text(html, encoding="utf-8")
    if not args.skip_email:
        config = AppConfig.from_env(dotenv_path=args.dotenv, require_email=True)
        _send(config, metrics, html)


def _fetch_and_enrich(
    target_date: date,
    *,
    fixture_dir: Path | None,
    dotenv_path: str,
) -> tuple[list[dict[str, Any]], list[EnrichedHistoryItem]]:
    if fixture_dir:
        transport = FixtureTransport(fixture_dir)
        client = BiliClient(
            sessdata="fixture",
            bili_jct="fixture",
            request_json=transport,
            sleep=lambda _: None,
            rate_limit_seconds=0,
        )
    else:
        config = AppConfig.from_env(dotenv_path=dotenv_path, require_email=False)
        client = BiliClient(
            sessdata=config.bili_sessdata,
            bili_jct=config.bili_bili_jct,
            rate_limit_seconds=config.rate_limit_seconds,
        )
    raw = client.fetch_history_for_day(target_date)
    return raw, client.enrich_items(raw, on_progress=_print_enrich_progress)


def _load_entries_for_report(
    output_dir: Path,
    target_date: date,
    *,
    fixture_dir: Path | None,
) -> list[EnrichedHistoryItem]:
    fixture_file = fixture_dir / f"enriched_{target_date.isoformat()}.json" if fixture_dir else None
    if fixture_file and fixture_file.exists():
        return [EnrichedHistoryItem.from_dict(item) for item in _read_json(fixture_file)]
    return _read_enriched(_enriched_path(output_dir, target_date))


def _render_site(
    output_dir: Path,
    target_date: date,
    metrics: DailyMetrics,
    entries: list[EnrichedHistoryItem],
) -> None:
    metrics_history = _load_metrics(output_dir)
    if not any(item.date == metrics.date for item in metrics_history):
        metrics_history.append(metrics)
    render_dashboard(
        output_dir=output_dir / "site",
        metrics_history=metrics_history,
        recent_entries={target_date.isoformat(): entries},
    )


def _send(config: AppConfig, metrics: DailyMetrics, html: str) -> None:
    smtp_config = SmtpConfig(
        host=config.smtp_host or "",
        port=config.smtp_port,
        user=config.smtp_user or "",
        password=config.smtp_password or "",
        mail_to=config.mail_to or "",
        mail_from=config.mail_from or config.smtp_user or "",
        use_ssl=config.smtp_use_ssl,
    )
    send_daily_email(
        config=smtp_config,
        subject=f"B 站观看日报 - {metrics.date}",
        html_body=html,
        attachments=[
            EmailAttachment(
                filename=f"bilibili-report-{metrics.date}.html",
                content=html.encode("utf-8"),
                maintype="text",
                subtype="html",
            )
        ],
    )


def _target_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    now = datetime.now(tz=SHANGHAI)
    return (now - timedelta(days=1)).date()


def _fixture_path(args: argparse.Namespace) -> Path | None:
    return Path(args.fixtures) if args.fixtures else None


def _raw_path(output_dir: Path, target_date: date) -> Path:
    return output_dir / "data" / "raw" / f"{target_date.isoformat()}.json"


def _enriched_path(output_dir: Path, target_date: date) -> Path:
    return output_dir / "data" / "enriched" / f"{target_date.isoformat()}.json"


def _metrics_path(output_dir: Path) -> Path:
    return output_dir / "data" / "metrics" / "daily.jsonl"


def _report_path(output_dir: Path, target_date: date) -> Path:
    path = output_dir / "data" / "reports" / f"{target_date.isoformat()}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_enriched(path: Path) -> list[EnrichedHistoryItem]:
    return [EnrichedHistoryItem.from_dict(item) for item in _read_json(path)]


def _metrics_for_date(output_dir: Path, target_date: date) -> DailyMetrics | None:
    for metric in _load_metrics(output_dir):
        if metric.date == target_date.isoformat():
            return metric
    return None


def _upsert_metrics(output_dir: Path, metrics: DailyMetrics) -> None:
    rows = [row for row in _load_metrics(output_dir) if row.date != metrics.date]
    rows.append(metrics)
    rows.sort(key=lambda row: row.date)
    path = _metrics_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row.to_dict(), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load_metrics(output_dir: Path) -> list[DailyMetrics]:
    path = _metrics_path(output_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(DailyMetrics.from_dict(json.loads(line)))
    return rows


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_enrich_progress(index: int, total: int) -> None:
    if total == 0:
        return
    if index == 1 or index == total or index % 25 == 0:
        print(f"Enriching video details: {index}/{total}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
