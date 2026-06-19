import json
from email.message import Message
from urllib.error import HTTPError

import bili_report.insights as insights
import pytest

from bili_report.comparison import build_daily_comparison
from bili_report.config import AppConfig
from bili_report.insights import build_ai_payload, generate_daily_insight
from bili_report.models import DailyMetrics


def make_metrics(
    day: int,
    *,
    total_records: int = 5,
    watch_seconds: int = 600,
    quick_ratio: float = 0.2,
) -> DailyMetrics:
    return DailyMetrics(
        date=f"2026-06-{day:02d}",
        total_records=total_records,
        unique_videos=total_records,
        short_video_count=2,
        long_video_count=3,
        estimated_watch_seconds=watch_seconds,
        total_duration_seconds=1200,
        completion_rate_avg=0.5,
        high_completion_video_count=2,
        high_completion_video_ratio=0.4,
        quick_exit_video_count=1,
        quick_exit_video_ratio=quick_ratio,
        top_authors=[{"name": "Alice", "count": 2}, {"name": "Bob", "count": 1}],
        top_categories=[{"name": "Tech", "count": 3}, {"name": "Music", "count": 1}],
        category_breakdown=[
            {"name": "Tech", "count": 3, "estimated_watch_seconds": 360, "total_duration_seconds": 700},
            {"name": "Music", "count": 1, "estimated_watch_seconds": 120, "total_duration_seconds": 250},
        ],
        warnings=["1 item used conservative watch-time estimate"],
    )


def make_config(**overrides: object) -> AppConfig:
    values = {
        "bili_sessdata": "cookie-secret",
        "bili_bili_jct": "csrf-secret",
        "smtp_host": "smtp.example.com",
        "smtp_user": "bot@example.com",
        "smtp_password": "mail-secret",
        "mail_to": "me@example.com",
        "ai_enabled": False,
        "ai_api_key": None,
        "ai_base_url": "https://api.example.com/v1",
        "ai_model": None,
        "ai_timeout_seconds": 20.0,
    }
    values.update(overrides)
    return AppConfig(**values)


def test_ai_disabled_uses_rule_based_insight_without_http_call() -> None:
    def fail_urlopen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("AI HTTP should not be called when disabled")

    insight = generate_daily_insight(
        make_metrics(17),
        [make_metrics(day) for day in range(11, 18)],
        config=make_config(ai_enabled=False),
        urlopen=fail_urlopen,
    )

    assert insight.source == "rules"
    assert "5 条" in insight.summary
    assert insight.encouragement
    assert insight.reminder
    assert insight.tomorrow_goal


def test_ai_success_uses_openai_compatible_payload_and_timeout() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, *, timeout: float) -> object:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "AI summary",
                                    "encouragement": "AI encouragement",
                                    "reminder": "AI reminder",
                                    "tomorrow_goal": "AI goal",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    insight = generate_daily_insight(
        make_metrics(17),
        [make_metrics(day) for day in range(1, 18)],
        config=make_config(
            ai_enabled=True,
            ai_api_key="ai-secret",
            ai_model="gpt-test",
            ai_timeout_seconds=7.5,
        ),
        urlopen=fake_urlopen,
    )

    assert insight.source == "ai"
    assert insight.summary == "AI summary"
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["timeout"] == 7.5
    assert captured["payload"]["model"] == "gpt-test"
    user_content = captured["payload"]["messages"][1]["content"]
    assert "last_7_days" in user_content
    assert "last_30_days" in user_content


def test_ai_default_transport_uses_certifi_ssl_context(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_context = object()

    def fake_create_default_context(*, cafile: str) -> object:
        captured["cafile"] = cafile
        return fake_context

    def fake_urlopen(request: object, *, timeout: float, context: object) -> object:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "AI summary",
                                    "encouragement": "AI encouragement",
                                    "reminder": "AI reminder",
                                    "tomorrow_goal": "AI goal",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(insights.certifi, "where", lambda: "/tmp/certifi-test.pem")
    monkeypatch.setattr(insights.ssl, "create_default_context", fake_create_default_context)
    monkeypatch.setattr(insights.request, "urlopen", fake_urlopen)

    insight = generate_daily_insight(
        make_metrics(17),
        [make_metrics(day) for day in range(1, 18)],
        config=make_config(
            ai_enabled=True,
            ai_api_key="ai-secret",
            ai_model="gpt-test",
            ai_timeout_seconds=7.5,
        ),
    )

    assert insight.source == "ai"
    assert captured["cafile"] == "/tmp/certifi-test.pem"
    assert captured["context"] is fake_context
    assert captured["timeout"] == 7.5
    assert captured["url"] == "https://api.example.com/v1/chat/completions"


@pytest.mark.parametrize(
    "urlopen",
    [
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError("https://api.example.com/v1/chat/completions", 500, "boom", Message(), None)
        ),
        lambda *_args, **_kwargs: FakeRawResponse(b"{not-json"),
        lambda *_args, **_kwargs: FakeResponse({"choices": [{"message": {"content": "{}"}}]}),
    ],
)
def test_ai_failures_fall_back_to_rules(urlopen: object) -> None:
    insight = generate_daily_insight(
        make_metrics(17),
        [make_metrics(day) for day in range(1, 18)],
        config=make_config(ai_enabled=True, ai_api_key="ai-secret", ai_model="gpt-test"),
        urlopen=urlopen,
    )

    assert insight.source == "rules"
    assert insight.summary
    assert insight.warnings


def test_missing_ai_key_or_model_falls_back_to_rules() -> None:
    insight = generate_daily_insight(
        make_metrics(17),
        [make_metrics(day) for day in range(1, 18)],
        config=make_config(ai_enabled=True, ai_api_key=None, ai_model=None),
        urlopen=lambda *_args, **_kwargs: pytest.fail("AI HTTP should not be called without key/model"),
    )

    assert insight.source == "rules"
    assert any("AI" in warning for warning in insight.warnings)


def test_ai_payload_contains_only_aggregate_metrics_and_trends() -> None:
    current = make_metrics(17)
    history = [make_metrics(day) for day in range(1, 18)]
    comparison = build_daily_comparison(current, history)
    payload = build_ai_payload(current, history, comparison=comparison)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["current_day"]["top_authors"][0] == {"name": "Alice", "count": 2}
    assert payload["trends"]["last_7_days"]["days"] == 7
    assert payload["trends"]["last_30_days"]["days"] == 17
    assert payload["comparison"]["vs_yesterday"]["available"] is True
    assert "category_changes" in payload["comparison"]["vs_recent_7d"]
    assert "title" not in serialized.lower()
    assert "raw" not in serialized.lower()
    assert "cookie-secret" not in serialized
    assert "mail-secret" not in serialized
    assert "bot@example.com" not in serialized
    assert "me@example.com" not in serialized


def test_rule_based_insight_uses_comparison_when_available() -> None:
    current = make_metrics(17, watch_seconds=900, quick_ratio=0.1)
    yesterday = make_metrics(16, watch_seconds=300, quick_ratio=0.5)

    insight = generate_daily_insight(
        current,
        [yesterday],
        config=make_config(ai_enabled=False),
        urlopen=lambda *_args, **_kwargs: pytest.fail("AI HTTP should not be called when disabled"),
    )

    assert "较昨日" in insight.summary
    assert "快速划走较昨日下降" in insight.reminder


class FakeResponse:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = json.dumps(data, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.data


class FakeRawResponse(FakeResponse):
    def __init__(self, data: bytes) -> None:
        self.data = data
