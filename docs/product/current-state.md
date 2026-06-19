# Current State

> Last updated: 2026-06-19
> Scope: target project current accepted state
> Responsibility: record what is currently true, accepted, and not to be misread
> Recommended next hop: `../architecture/system-map.md`

## Current Phase

Local MVP is implemented in `bilibili-watch-report/` and is being refined through local runs before cloud automation is finalized.

## Accepted Capabilities

- The project can read saved/enriched Bilibili watch records, compute daily metrics, generate `data/reports/YYYY-MM-DD.html`, update `data/metrics/daily.jsonl`, and render `site/index.html` plus `site/data.json`.
- The daily report HTML uses the design direction in `/Users/garytchois/Desktop/bilibli/日报HTML设计方案/B站观看日报.dc.html`: Bilibili pink/blue palette, KPI strip, donut/gauge visuals, viewing-behavior distribution, Top UP/category bars, recent-watch list, and estimation footnote.
- The generated daily report is standalone full visual HTML for `data/reports/YYYY-MM-DD.html` and email attachment use. It intentionally does not include the design tool runtime wrapper, `support.js`, or inline scripts.
- Email sending uses a separate compact table-based HTML body for mobile/QQ Mail compatibility, while attaching the full visual HTML report.
- Daily aggregate metrics now retain full per-category aggregate breakdown (`category_breakdown`: name, count, estimated watch seconds, total duration seconds) without titles/details, and reports can compare the current day against yesterday and the prior available 7 daily metric rows. The compact email, full HTML report, dashboard data/table, and AI/rule insight path consume this aggregate-only comparison data.
- Daily email insight text is generated locally by rules by default. Optional OpenAI-compatible AI insight generation is opt-in through `AI_ENABLED=true`, `AI_API_KEY`, and `AI_MODEL`, and failures fall back to rules without blocking email sending.
- The active GitHub Actions workflow for the current repository layout is the repository-root `.github/workflows/daily.yml`, with commands running inside `bilibili-watch-report/`. Scheduled runs execute at `00:13 UTC` / `08:13 Asia/Shanghai`, send the previous day's email automatically, and manual runs default to `send_email=false` for safe testing.

## Standing Contracts

- Do not directly run email-sending commands unless the user explicitly authorizes sending in that turn.
- Keep `.env`, Bilibili cookies, SMTP credentials, and private generated data out of logs and docs.
- The report should show viewing ratio as estimated watch time divided by total watchable video duration, not as a standalone “video total duration” KPI.

## Known Non-Goals

TBD.

## Do Not Misread

TBD.
