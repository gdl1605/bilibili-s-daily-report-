from datetime import date, datetime
import ssl
from zoneinfo import ZoneInfo

import pytest

from bili_report import client as client_module
from bili_report.client import AuthenticationError, BiliClient


def shanghai_ts(year: int, month: int, day: int, hour: int) -> int:
    return int(datetime(year, month, day, hour, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())


class FakeTransport:
    def __init__(self) -> None:
        self.history_calls: list[dict] = []
        self.detail_calls: list[dict] = []
        self.history_pages = [
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "title": "Morning video",
                            "author_name": "Alice",
                            "view_at": shanghai_ts(2026, 6, 17, 10),
                            "progress": 120,
                            "history": {"bvid": "BV1", "oid": 101, "business": "archive"},
                        },
                        {
                            "title": "Noon video",
                            "author_name": "Bob",
                            "view_at": shanghai_ts(2026, 6, 17, 12),
                            "progress": 60,
                            "history": {"bvid": "BV2", "oid": 102, "business": "archive"},
                        },
                    ]
                },
            },
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "title": "Previous day",
                            "author_name": "Carol",
                            "view_at": shanghai_ts(2026, 6, 16, 23),
                            "progress": 20,
                            "history": {"bvid": "BVold", "oid": 99, "business": "archive"},
                        }
                    ]
                },
            },
        ]
        self.video_details = {
            "BV1": {
                "code": 0,
                "data": {
                    "bvid": "BV1",
                    "aid": 1,
                    "title": "Morning video detail",
                    "duration": 180,
                    "tname": "Music",
                    "owner": {"name": "Alice"},
                },
            },
            "BV2": {
                "code": 0,
                "data": {
                    "bvid": "BV2",
                    "aid": 2,
                    "title": "Noon video detail",
                    "duration": 600,
                    "tname": "Tech",
                    "owner": {"name": "Bob"},
                },
            },
        }

    def __call__(self, url: str, params: dict, headers: dict) -> dict:
        assert "SESSDATA=sess-value" in headers["Cookie"]
        if "history/cursor" in url:
            self.history_calls.append(dict(params))
            return self.history_pages[len(self.history_calls) - 1]
        if "web-interface/view" in url:
            self.detail_calls.append(dict(params))
            return self.video_details[params["bvid"]]
        raise AssertionError(f"unexpected URL: {url}")


def test_history_fetch_uses_cursor_and_stops_after_target_date() -> None:
    transport = FakeTransport()
    client = BiliClient(
        sessdata="sess-value",
        bili_jct="jct-value",
        request_json=transport,
        sleep=lambda _: None,
        rate_limit_seconds=0,
    )

    items = client.fetch_history_for_day(date(2026, 6, 17))

    assert [item["title"] for item in items] == ["Morning video", "Noon video"]
    assert len(transport.history_calls) == 2
    assert transport.history_calls[0]["type"] == "all"
    assert transport.history_calls[0]["ps"] == 20
    assert transport.history_calls[1]["max"] == 102
    assert transport.history_calls[1]["business"] == "archive"
    assert transport.history_calls[1]["view_at"] == shanghai_ts(2026, 6, 17, 12)


def test_history_fetch_turns_login_error_into_authentication_error() -> None:
    def transport(url: str, params: dict, headers: dict) -> dict:
        return {"code": -101, "message": "账号未登录", "ttl": 1}

    client = BiliClient(
        sessdata="expired",
        bili_jct="jct",
        request_json=transport,
        sleep=lambda _: None,
        rate_limit_seconds=0,
    )

    with pytest.raises(AuthenticationError, match="账号未登录"):
        client.fetch_history_for_day(date(2026, 6, 17))


def test_enrich_items_fetches_video_details_and_keeps_history_progress() -> None:
    transport = FakeTransport()
    client = BiliClient(
        sessdata="sess-value",
        bili_jct="jct-value",
        request_json=transport,
        sleep=lambda _: None,
        rate_limit_seconds=0,
    )

    history_items = client.fetch_history_for_day(date(2026, 6, 17))
    enriched = client.enrich_items(history_items)

    assert [item.duration for item in enriched] == [180, 600]
    assert [item.tname for item in enriched] == ["Music", "Tech"]
    assert [item.progress for item in enriched] == [120, 60]
    assert transport.detail_calls == [{"bvid": "BV1"}, {"bvid": "BV2"}]


def test_enrich_items_keeps_history_item_when_video_detail_is_unavailable() -> None:
    def transport(url: str, params: dict, headers: dict) -> dict:
        if "web-interface/view" in url:
            return {"code": -403, "message": "稿件不可见", "ttl": 1}
        raise AssertionError(f"unexpected URL: {url}")

    client = BiliClient(
        sessdata="sess-value",
        bili_jct="jct-value",
        request_json=transport,
        sleep=lambda _: None,
        rate_limit_seconds=0,
    )

    enriched = client.enrich_items(
        [
            {
                "title": "Unavailable from history",
                "author_name": "Hidden",
                "view_at": shanghai_ts(2026, 6, 17, 10),
                "progress": 42,
                "history": {"bvid": "BVgone", "oid": 404, "business": "archive"},
            }
        ]
    )

    assert enriched[0].title == "Unavailable from history"
    assert enriched[0].bvid == "BVgone"
    assert enriched[0].duration is None


def test_default_request_json_uses_a_ca_verified_ssl_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"code": 0, "data": {"ok": true}}'

    def fake_urlopen(request, timeout: int, context: ssl.SSLContext):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    payload = client_module._default_request_json(
        "https://api.bilibili.com/test",
        {"bvid": "BV1"},
        {"User-Agent": "test"},
    )

    assert payload == {"code": 0, "data": {"ok": True}}
    assert captured["timeout"] == 10
    assert isinstance(captured["context"], ssl.SSLContext)
