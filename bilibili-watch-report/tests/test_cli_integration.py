from pathlib import Path

import bili_report.cli as cli
from bili_report.cli import main


def test_build_report_from_enriched_fixture_generates_metrics_and_site(tmp_path: Path) -> None:
    exit_code = main(
        [
            "build-report",
            "--date",
            "2026-06-17",
            "--fixtures",
            "tests/fixtures",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "data" / "metrics" / "daily.jsonl").exists()
    assert (tmp_path / "site" / "index.html").exists()


def test_run_daily_with_fixtures_generates_raw_enriched_metrics_and_site(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run-daily",
            "--date",
            "2026-06-17",
            "--fixtures",
            "tests/fixtures",
            "--output-dir",
            str(tmp_path),
            "--skip-email",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "data" / "raw" / "2026-06-17.json").exists()
    assert (tmp_path / "data" / "enriched" / "2026-06-17.json").exists()
    assert (tmp_path / "data" / "metrics" / "daily.jsonl").exists()
    assert (tmp_path / "site" / "data.json").exists()


def test_run_daily_skip_email_does_not_call_ai_or_send_email(tmp_path: Path, monkeypatch) -> None:
    def fail_generate(*_args, **_kwargs):
        raise AssertionError("AI insight should not be generated when --skip-email is used")

    def fail_send(*_args, **_kwargs):
        raise AssertionError("Email should not be sent when --skip-email is used")

    monkeypatch.setattr(cli, "generate_daily_insight", fail_generate)
    monkeypatch.setattr(cli, "send_daily_email", fail_send)

    exit_code = main(
        [
            "run-daily",
            "--date",
            "2026-06-17",
            "--fixtures",
            "tests/fixtures",
            "--output-dir",
            str(tmp_path),
            "--skip-email",
        ]
    )

    assert exit_code == 0


def test_send_email_uses_compact_body_and_full_report_attachment(tmp_path: Path, monkeypatch) -> None:
    exit_code = main(
        [
            "build-report",
            "--date",
            "2026-06-17",
            "--fixtures",
            "tests/fixtures",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    dotenv = tmp_path / "test.env"
    dotenv.write_text(
        "\n".join(
            [
                "BILI_SESSDATA=sess",
                "BILI_BILI_JCT=jct",
                "SMTP_HOST=smtp.example.com",
                "SMTP_USER=bot@example.com",
                "SMTP_PASSWORD=mail-secret",
                "MAIL_TO=me@example.com",
                "AI_ENABLED=false",
            ]
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_send_daily_email(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "send_daily_email", fake_send_daily_email)

    exit_code = main(
        [
            "send-email",
            "--date",
            "2026-06-17",
            "--output-dir",
            str(tmp_path),
            "--dotenv",
            str(dotenv),
        ]
    )

    assert exit_code == 0
    body = captured["html_body"]
    attachment = captured["attachments"][0]
    attachment_html = attachment.content.decode("utf-8")
    assert "B 站观看日报速览" in body
    assert "今日洞察" in body
    assert "变化速览" in body
    assert "<table" in body.lower()
    assert "<svg" not in body.lower()
    assert "display:grid" not in body.lower()
    assert "Space Grotesk" not in body
    assert attachment.filename == "bilibili-report-2026-06-17.html"
    assert "<svg" in attachment_html.lower()
    assert "Space Grotesk" in attachment_html
    assert body != attachment_html
