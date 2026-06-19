# Bilibili Watch Report

Private daily Bilibili watch-history analytics. The project fetches your own Bilibili history, estimates daily watch time, sends a compact email body with the full visual HTML report attached, and generates a static dashboard.

## What It Tracks

- Daily history record count and unique video count.
- Long versus short video count.
- Estimated watch time from `progress`, clipped to `[0, duration]`.
- Total video duration.
- Top authors and categories.
- Daily insight summary, encouragement, reminder, and tomorrow goal.
- A static dashboard for the latest 30 days.

Short-video classification prefers any explicit API signal when present. If Bilibili does not provide one, videos shorter than 180 seconds are treated as short videos.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
```

Fill `.env` with:

- `BILI_SESSDATA` and `BILI_BILI_JCT` from your logged-in Bilibili browser cookies.
- `BILI_RATE_LIMIT_SECONDS`, the delay between Bilibili requests. The default `0.3` is meant for personal daily use.
- SMTP settings for the mailbox that sends the report.
- `MAIL_TO` for the recipient.
- Optional AI insight settings. `AI_ENABLED=false` by default; set `AI_ENABLED=true`, `AI_API_KEY`, and `AI_MODEL` only if you want to use an OpenAI-compatible chat-completions endpoint.

Keep `.env` private. Do not paste cookies into logs, issues, or commits.

## Local Commands

Run tests:

```bash
.venv/bin/python -m pytest
```

Build a report from the included offline fixtures:

```bash
.venv/bin/python -m bili_report.cli build-report --date 2026-06-17 --fixtures tests/fixtures
```

Fetch and report a real day without sending email:

```bash
.venv/bin/python -m bili_report.cli run-daily --date 2026-06-17 --skip-email
```

Run the full daily job and send email:

```bash
.venv/bin/python -m bili_report.cli run-daily --date 2026-06-17
```

Outputs:

- `data/raw/YYYY-MM-DD.json`
- `data/enriched/YYYY-MM-DD.json`
- `data/metrics/daily.jsonl`
- `data/reports/YYYY-MM-DD.html`
- `site/index.html` and `site/data.json`

Email behavior:

- `build-report` writes the full visual HTML report to `data/reports/YYYY-MM-DD.html`.
- `send-email` and `run-daily` use a compact table-based email body for better mobile and QQ Mail compatibility.
- The full visual HTML report is still attached to the email as `bilibili-report-YYYY-MM-DD.html`.

## GitHub Actions

When this app lives under the repository root `bilibili-watch-report/`, the active workflow should be at the repository-level path `.github/workflows/daily.yml`. It runs at 00:13 UTC, which is 08:13 in Asia/Shanghai, and reports the previous day by default. The schedule intentionally avoids the top of the hour because GitHub Actions scheduled runs can be delayed or dropped during hourly load spikes. It also supports manual `workflow_dispatch`.

Manual runs default to `send_email=false` for safer testing. Scheduled runs send the daily email automatically.

Add these repository secrets:

- `BILI_SESSDATA`
- `BILI_BILI_JCT`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_USE_SSL`
- `MAIL_TO`
- `MAIL_FROM`
- Optional AI secrets: `AI_ENABLED`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT_SECONDS`

The workflow commits `data/` and `site/` back to the repository. Use a private repository unless you intentionally want these aggregates stored publicly.

## GitHub Pages

Publishing is fail-closed. The workflow uploads `site/` as an artifact every run, but deploys Pages only when `PUBLISH_PAGES=true`.

Recommended setup:

1. Keep the repository private.
2. Confirm your GitHub plan supports private Pages for this repository.
3. Add a repository variable `PUBLISH_PAGES` with value `true`.
4. Configure Pages to deploy from GitHub Actions.

If private Pages is unavailable or you leave `PUBLISH_PAGES=false`, the email still sends and the dashboard remains available as a workflow artifact and committed `site/` output.

## Privacy And Stability Notes

This is intended for personal use only. Bilibili history access depends on non-public web APIs and your login cookies, so it may break if Bilibili changes endpoints, response fields, anti-bot behavior, or cookie requirements.

The client is intentionally low frequency: the scheduled job runs once per day, requests are rate-limited, and retry behavior is conservative. If the cookie expires, the job fails with an authentication error instead of trying to bypass login.

AI insights are opt-in and fail open to local rules: missing AI settings, timeouts, HTTP failures, bad JSON, or incomplete AI output do not block email sending. When enabled, the AI payload is limited to aggregate daily metrics, Top UP/category counts, and 7/30-day trend aggregates. It must not include video titles, raw/enriched history, cookies, SMTP credentials, email addresses, or full request headers.

Known rendering limitation: QQ Mail and some mobile attachment viewers may not render inline SVG charts in the attached full HTML report and may show `[SVG Image]` placeholders. The compact email body avoids SVG; replacing full-report SVG charts with image or non-SVG HTML charts is a future improvement.
