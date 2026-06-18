from pathlib import Path

import pytest

from bili_report.config import AppConfig, ConfigError


def test_config_loads_dotenv_and_masks_secrets(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "BILI_SESSDATA=sess-value",
                "BILI_BILI_JCT=jct-value",
                "SMTP_HOST=smtp.example.com",
                "SMTP_USER=bot@example.com",
                "SMTP_PASSWORD=mail-secret",
                "MAIL_TO=me@example.com",
                "MAIL_FROM=reports@example.com",
                "PUBLISH_PAGES=true",
                "BILI_RATE_LIMIT_SECONDS=0.3",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env(env={}, dotenv_path=dotenv, require_email=True)

    assert config.bili_sessdata == "sess-value"
    assert config.bili_bili_jct == "jct-value"
    assert config.smtp_host == "smtp.example.com"
    assert config.mail_from == "reports@example.com"
    assert config.publish_pages is True
    assert config.rate_limit_seconds == 0.3
    assert config.safe_dict()["BILI_SESSDATA"] == "***"
    assert config.safe_dict()["SMTP_PASSWORD"] == "***"


def test_config_reports_missing_required_secret() -> None:
    with pytest.raises(ConfigError, match="BILI_SESSDATA"):
        AppConfig.from_env(env={}, dotenv_path=None, require_email=False)


def test_config_allows_fetch_without_email_settings() -> None:
    config = AppConfig.from_env(
        env={"BILI_SESSDATA": "sess", "BILI_BILI_JCT": "jct"},
        dotenv_path=None,
        require_email=False,
    )

    assert config.smtp_host is None
    assert config.mail_to is None
