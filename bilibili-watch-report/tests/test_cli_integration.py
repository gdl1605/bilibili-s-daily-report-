from pathlib import Path

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
