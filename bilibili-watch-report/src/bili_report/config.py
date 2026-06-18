from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    bili_sessdata: str
    bili_bili_jct: str
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_to: str | None = None
    mail_from: str | None = None
    smtp_use_ssl: bool = True
    publish_pages: bool = False
    rate_limit_seconds: float = 0.3

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        dotenv_path: Path | str | None = ".env",
        require_email: bool = True,
    ) -> "AppConfig":
        values: dict[str, str] = {}
        if dotenv_path is not None:
            path = Path(dotenv_path)
            if path.exists():
                values.update(_read_dotenv(path))
        values.update(dict(os.environ if env is None else env))

        missing = [name for name in ("BILI_SESSDATA", "BILI_BILI_JCT") if not values.get(name)]
        if require_email:
            missing.extend(
                name
                for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")
                if not values.get(name)
            )
        if missing:
            raise ConfigError(f"Missing required configuration: {', '.join(missing)}")

        smtp_port = int(values.get("SMTP_PORT") or 465)
        smtp_use_ssl = _parse_bool(values.get("SMTP_USE_SSL"), default=smtp_port == 465)
        smtp_user = values.get("SMTP_USER")

        return cls(
            bili_sessdata=values["BILI_SESSDATA"],
            bili_bili_jct=values["BILI_BILI_JCT"],
            smtp_host=values.get("SMTP_HOST"),
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=values.get("SMTP_PASSWORD"),
            mail_to=values.get("MAIL_TO"),
            mail_from=values.get("MAIL_FROM") or smtp_user,
            smtp_use_ssl=smtp_use_ssl,
            publish_pages=_parse_bool(values.get("PUBLISH_PAGES"), default=False),
            rate_limit_seconds=float(values.get("BILI_RATE_LIMIT_SECONDS") or 0.3),
        )

    def safe_dict(self) -> dict[str, str | int | bool | None]:
        return {
            "BILI_SESSDATA": "***",
            "BILI_BILI_JCT": "***",
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASSWORD": "***" if self.smtp_password else None,
            "MAIL_TO": self.mail_to,
            "MAIL_FROM": self.mail_from,
            "SMTP_USE_SSL": self.smtp_use_ssl,
            "PUBLISH_PAGES": self.publish_pages,
            "BILI_RATE_LIMIT_SECONDS": self.rate_limit_seconds,
        }


def _read_dotenv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
