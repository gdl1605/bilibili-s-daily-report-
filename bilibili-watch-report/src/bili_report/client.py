from __future__ import annotations

import json
import ssl
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import certifi

from .models import EnrichedHistoryItem

HISTORY_URL = "https://api.bilibili.com/x/web-interface/history/cursor"
VIDEO_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
SHANGHAI = ZoneInfo("Asia/Shanghai")

RequestJson = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
ProgressCallback = Callable[[int, int], None]


class BiliApiError(RuntimeError):
    """Raised when Bilibili returns a non-successful API response."""


class AuthenticationError(BiliApiError):
    """Raised when the Bilibili cookie is missing, expired, or rejected."""


class BiliClient:
    def __init__(
        self,
        *,
        sessdata: str,
        bili_jct: str,
        request_json: RequestJson | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rate_limit_seconds: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.sessdata = sessdata
        self.bili_jct = bili_jct
        self.request_json = request_json or _default_request_json
        self.sleep = sleep
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self._last_request_at: float | None = None

    def fetch_history_for_day(self, target_date: date) -> list[dict[str, Any]]:
        start_ts, end_ts = _day_bounds(target_date)
        params: dict[str, Any] = {"type": "all", "ps": 20}
        results: list[dict[str, Any]] = []
        seen_cursors: set[tuple[Any, Any, Any]] = set()

        for _ in range(50):
            payload = self._api_get(HISTORY_URL, params)
            data = payload.get("data") or {}
            page_items = list(data.get("list") or [])
            if not page_items:
                break

            for item in page_items:
                view_at = int(item.get("view_at") or 0)
                if start_ts <= view_at < end_ts:
                    results.append(item)

            if any(int(item.get("view_at") or 0) < start_ts for item in page_items):
                break

            next_params = _next_cursor_params(data, page_items)
            cursor_key = (
                next_params.get("max"),
                next_params.get("business"),
                next_params.get("view_at"),
            )
            if not all(cursor_key) or cursor_key in seen_cursors:
                break
            seen_cursors.add(cursor_key)
            params = {"type": "all", "ps": 20, **next_params}

        return results

    def enrich_items(
        self,
        history_items: list[dict[str, Any]],
        *,
        on_progress: ProgressCallback | None = None,
    ) -> list[EnrichedHistoryItem]:
        enriched: list[EnrichedHistoryItem] = []
        total = len(history_items)
        for index, item in enumerate(history_items, start=1):
            if on_progress:
                on_progress(index, total)
            history = item.get("history") or {}
            business = history.get("business") or item.get("business")
            detail: dict[str, Any] | None = None
            if business in {"archive", "pgc"}:
                detail = self._fetch_video_detail(history)
            enriched.append(EnrichedHistoryItem.from_api(item, detail))
        return enriched

    def _fetch_video_detail(self, history: dict[str, Any]) -> dict[str, Any] | None:
        bvid = history.get("bvid")
        aid = history.get("oid") if history.get("business") == "archive" else history.get("aid")
        try:
            if bvid:
                payload = self._api_get(VIDEO_VIEW_URL, {"bvid": bvid})
            elif aid:
                payload = self._api_get(VIDEO_VIEW_URL, {"aid": aid})
            else:
                return None
        except AuthenticationError:
            raise
        except BiliApiError:
            return None
        return payload.get("data") or {}

    def _api_get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        clean_params = {key: value for key, value in params.items() if value is not None}
        headers = self._headers()
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                payload = self.request_json(url, clean_params, headers)
                code = int(payload.get("code", 0))
                if code == 0:
                    return payload
                message = str(payload.get("message") or f"Bilibili API error {code}")
                if code == -101:
                    raise AuthenticationError(message)
                if code in {-412, -503, -509} and attempt < self.max_retries:
                    self.sleep(2 ** (attempt - 1))
                    continue
                raise BiliApiError(message)
            except AuthenticationError:
                raise
            except BiliApiError:
                raise
            except Exception as exc:  # noqa: BLE001 - retry transport-level failures.
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self.sleep(2 ** (attempt - 1))

        raise BiliApiError(f"Bilibili request failed after {self.max_retries} attempts: {last_error}")

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (compatible; bili-report/0.1)",
            "Referer": "https://www.bilibili.com/account/history",
            "Cookie": f"SESSDATA={self.sessdata}; bili_jct={self.bili_jct}",
        }

    def _throttle(self) -> None:
        if self.rate_limit_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.rate_limit_seconds:
                self.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_at = time.monotonic()


def _day_bounds(target_date: date) -> tuple[int, int]:
    start = datetime.combine(target_date, datetime.min.time(), tzinfo=SHANGHAI)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _next_cursor_params(data: dict[str, Any], page_items: list[dict[str, Any]]) -> dict[str, Any]:
    cursor = data.get("cursor") or {}
    last = page_items[-1]
    last_history = last.get("history") or {}
    return {
        "max": cursor.get("max") or last_history.get("oid") or last.get("oid"),
        "business": cursor.get("business") or last_history.get("business") or last.get("business"),
        "view_at": cursor.get("view_at") or last.get("view_at"),
    }


def _default_request_json(url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    query = urlencode(params)
    request_url = f"{url}?{query}" if query else url
    request = Request(request_url, headers=headers, method="GET")
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=10, context=context) as response:  # noqa: S310 - user-controlled private automation.
        body = response.read().decode("utf-8")
    return json.loads(body)
