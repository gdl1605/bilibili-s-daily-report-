from datetime import date
from email.message import EmailMessage
from pathlib import Path

from bili_report.emailer import EmailAttachment, SmtpConfig, send_daily_email
from bili_report.models import DailyInsight, DailyMetrics, EnrichedHistoryItem
from bili_report.report import build_compact_email_html, build_email_html, render_dashboard


class FakeSMTP:
    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logged_in: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []
        self.started_tls = False

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


def metrics() -> DailyMetrics:
    return DailyMetrics(
        date="2026-06-17",
        total_records=3,
        unique_videos=3,
        short_video_count=2,
        long_video_count=1,
        estimated_watch_seconds=680,
        total_duration_seconds=1200,
        completion_rate_avg=0.57,
        high_completion_video_count=1,
        high_completion_video_ratio=0.3333,
        quick_exit_video_count=1,
        quick_exit_video_ratio=0.3333,
        top_authors=[{"name": "Alice", "count": 2}],
        top_categories=[{"name": "Tech", "count": 2}],
        warnings=["1 item used conservative watch-time estimate"],
    )


def entries() -> list[EnrichedHistoryItem]:
    return [
        EnrichedHistoryItem(
            title="Morning video",
            bvid="BV1",
            aid=1,
            author_name="Alice",
            business="archive",
            view_at=1781652000,
            progress=120,
            duration=180,
            tname="Music",
            raw={},
        )
    ]


def test_email_html_contains_core_metrics_and_estimation_notice() -> None:
    html = build_email_html(metrics(), entries(), dashboard_url="https://example.com/report")

    assert "2026-06-17" in html
    assert "3" in html
    assert "估算" in html
    assert "观看占比" in html
    assert "56.7%" in html
    assert "看完 80%+" in html
    assert "15s 内退出" in html
    assert "33.3%" in html
    assert "视频总时长" not in html
    assert "可看总时长" not in html
    assert "可看时长共" not in html
    assert "https://example.com/report" in html
    assert "Alice" in html


def test_email_html_matches_daily_design_shell_without_runtime_scripts() -> None:
    html = build_email_html(metrics(), entries(), dashboard_url="https://example.com/report")

    assert "Bilibili · 每日观看洞察" in html
    assert "2026年6月17日" in html
    assert "星期三 · 全天观看行为汇总" in html
    assert "短视频 vs 长视频" in html
    assert "观看时长占比" in html
    assert "观看行为分布" in html
    assert "Top UP 主" in html
    assert "Top 分区" in html
    assert "最近观看" in html
    assert "#FB7299" in html
    assert "#00AEEC" in html
    assert "Space Grotesk" in html
    assert "Plus Jakarta Sans" in html
    assert "support.js" not in html
    assert "<script" not in html.lower()
    assert "<x-dc" not in html.lower()


def test_compact_email_body_is_mobile_and_qq_friendly() -> None:
    body = build_compact_email_html(
        metrics(),
        DailyInsight(
            summary="今天看了 3 条，估算观看 11m 20s。",
            encouragement="高完成观看已经出现，节奏不错。",
            reminder="记得给眼睛留一点休息时间。",
            tomorrow_goal="明天先挑 1 个高质量长视频慢慢看。",
            source="rules",
            warnings=[],
        ),
        dashboard_url="https://example.com/report",
    )
    lowered = body.lower()

    assert "今天看了 3 条" in body
    assert "高完成观看已经出现" in body
    assert "记得给眼睛" in body
    assert "明天先挑" in body
    assert "估算观看时长" in body
    assert "观看占比" in body
    assert "平均完成率" in body
    assert "Top UP 主" in body
    assert "Top 分区" in body
    assert "Alice" in body
    assert "Tech" in body
    assert "https://example.com/report" in body
    assert "<table" in lowered
    assert "<svg" not in lowered
    assert "<script" not in lowered
    assert "fonts.googleapis" not in lowered
    assert "@keyframes" not in lowered
    assert "display:grid" not in lowered
    assert "grid-template" not in lowered
    assert "可看总时长" not in body
    assert "可看时长共" not in body


def test_dashboard_renders_static_html_and_json(tmp_path: Path) -> None:
    render_dashboard(output_dir=tmp_path, metrics_history=[metrics()], recent_entries={"2026-06-17": entries()})

    assert (tmp_path / "index.html").exists()
    data = (tmp_path / "data.json").read_text(encoding="utf-8")
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '"date": "2026-06-17"' in data
    assert "Bilibili Watch Report" in html
    assert "Watch Ratio" in html
    assert "80%+ Watched" in html
    assert "15s Exit" in html
    assert "Total Duration" not in html


def test_send_daily_email_uses_smtp_config_and_html_body() -> None:
    smtp = FakeSMTP("smtp.example.com", 587)

    def smtp_factory(host: str, port: int, timeout: int = 30) -> FakeSMTP:
        assert host == "smtp.example.com"
        assert port == 587
        return smtp

    config = SmtpConfig(
        host="smtp.example.com",
        port=587,
        user="bot@example.com",
        password="secret",
        mail_to="me@example.com",
        mail_from="reports@example.com",
        use_ssl=False,
    )

    send_daily_email(
        config=config,
        subject="Daily report",
        html_body="<h1>Hello</h1>",
        attachments=[
            EmailAttachment(
                filename="daily-report.html",
                content=b"<h1>Hello</h1>",
                maintype="text",
                subtype="html",
            )
        ],
        smtp_factory=smtp_factory,
    )

    assert smtp.started_tls is True
    assert smtp.logged_in == ("bot@example.com", "secret")
    assert smtp.messages[0]["To"] == "me@example.com"
    assert smtp.messages[0]["From"] == "reports@example.com"
    assert smtp.messages[0]["Subject"] == "Daily report"
    attachment = next(part for part in smtp.messages[0].iter_attachments())
    assert attachment.get_filename() == "daily-report.html"
    assert attachment.get_content_type() == "text/html"
