# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup and run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

App runs at http://127.0.0.1:5000. There are no lint, test, or build commands configured — no test suite exists yet.

## Architecture

Single-process Flask app, four modules:

- `app.py` — `create_app()` builds the Flask app, wires SQLAlchemy to a local SQLite file (`stock_monitor.db`, gitignored), and creates tables on startup. All routes live directly in this file (no blueprints). `app = create_app()` is a module-level singleton. `start_scheduler(app)` is only invoked in the `if __name__ == "__main__"` block, so the background poller does not run under `flask run` or a WSGI server that imports `app.py` without executing it as `__main__`.
- `models.py` — three SQLAlchemy models: `Ticker` (watchlist entry with cached `last_price`/`last_change_pct`), `Alert` (belongs to a `Ticker`, one-shot: `active` flips to `False` once `triggered_at` is set, it does not re-trigger), `Notification` (flat list, `read` boolean drives the unread-count badge).
- `stock_data.py` — the only module that talks to `yfinance`. Every function returns `None`/`(None, None)`/`[]` on failure instead of raising, so callers never need try/except around price data — this is what lets the app "degrade gracefully" on Yahoo Finance outages/rate-limits.
- `scheduler.py` — an APScheduler `BackgroundScheduler` polls every ticker's price every 60s (`POLL_INTERVAL_SECONDS`), updates cached price fields, and evaluates every active `Alert` for that ticker; a crossed alert deactivates itself and writes a `Notification` row in the same commit.

Templates (`templates/`) are server-rendered Jinja with routes doing full-page or redirect-based updates (no SPA/JS framework) — `base.html` is the shared layout with the alerts bell, `dashboard.html`/`ticker.html`/`notifications.html` extend it.

### Request flow for prices

Ticker prices shown on the dashboard are the *cached* `last_price`/`last_change_pct` columns, refreshed only by the background scheduler — routes never fetch a live quote for display except when adding a new ticker (`symbol_exists` + `fetch_quote` in `add_ticker`) or loading history (`ticker_detail` calls `fetch_history` live, per request, uncached).
