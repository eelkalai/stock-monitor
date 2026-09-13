# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup and run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

App runs at http://127.0.0.1:5000. There are no lint, test, or build commands configured — no test suite exists yet.

## Product overview

Local single-user Flask app for tracking a stock watchlist. Current capabilities:

- **Watchlist**: add a ticker by symbol (validated against Yahoo Finance before saving, rejects unknown symbols inline), remove a ticker (cascades its alerts), dashboard lists all tickers alphabetically with cached last price and % change.
- **Price data**: background poller refreshes every ticker's price/change every 60s and caches it — the dashboard always reads from cache, never live, except when adding a ticker. Per-ticker historical chart with selectable range (1mo/3mo/6mo/1y/5y), fetched live per request. Any Yahoo Finance failure/rate-limit degrades to an empty result instead of erroring the page.
- **Alerts**: set an "above"/"below" price threshold per ticker, delete an alert. One-shot — once triggered the alert deactivates and won't re-fire.
- **Notifications**: bell icon with unread-count badge (polled via `/api/notifications/unread-count`), notifications page lists triggered alerts newest-first and marks them all read on view.
- **Live-update switch**: topbar toggle to pause/resume the background price poller (in-memory only, resets to on across restarts). Adding a ticker and viewing a chart still fetch live regardless of this switch.
- **Screeners**: drop-in Python scripts in `scripts/` implement custom stock-screening algorithms (not limited to the watchlist — a script can fetch/screen any symbols it wants, e.g. via `yfinance`'s `yf.screen()`). The `/screeners` page lists discovered scripts and runs one on demand; each run is isolated in its own subprocess with a timeout, so a hung or crashing script can't take down the app. Results are ephemeral (not persisted) and rendered directly on the page.

Not present: no auth/multi-user support, no tests, no JSON API beyond the one unread-count endpoint, no editing of existing tickers/alerts (only add/delete). Any change to capabilities, design, or scope should be reflected in this section so it stays the source of truth for what the product currently does.

## Architecture

Single-process Flask app, five modules:

- `app.py` — `create_app()` builds the Flask app, wires SQLAlchemy to a local SQLite file (`stock_monitor.db`, gitignored), and creates tables on startup. All routes live directly in this file (no blueprints). `app = create_app()` is a module-level singleton. `start_scheduler(app)` is only invoked in the `if __name__ == "__main__"` block, so the background poller does not run under `flask run` or a WSGI server that imports `app.py` without executing it as `__main__`. `app.config["POLLING_ENABLED"]` (in-memory) gates the background poller and is injected into every template via a context processor.
- `models.py` — three SQLAlchemy models: `Ticker` (watchlist entry with cached `last_price`/`last_change_pct`), `Alert` (belongs to a `Ticker`, one-shot: `active` flips to `False` once `triggered_at` is set, it does not re-trigger), `Notification` (flat list, `read` boolean drives the unread-count badge).
- `stock_data.py` — the only module that talks to `yfinance`. Every function returns `None`/`(None, None)`/`[]` on failure instead of raising, so callers never need try/except around price data — this is what lets the app "degrade gracefully" on Yahoo Finance outages/rate-limits.
- `scheduler.py` — an APScheduler `BackgroundScheduler` polls every ticker's price every 60s (`POLL_INTERVAL_SECONDS`), updates cached price fields, and evaluates every active `Alert` for that ticker; a crossed alert deactivates itself and writes a `Notification` row in the same commit. `poll_prices` no-ops immediately (but keeps firing on schedule) while `POLLING_ENABLED` is false.
- `screeners.py` — discovers screener scripts in `scripts/*.py` (`list_screeners`) and runs one by name (`run_screener`) as an isolated subprocess (`sys.executable`, so it shares the venv) with a timeout, parsing its stdout as a JSON list of `{"symbol": ..., "price": ..., "change_pct": ..., "note": ...}` results. Mirrors `stock_data.py`'s never-raise convention — every failure (unknown name, timeout, non-zero exit, bad JSON) returns `(None, "error string")` instead of raising.

Templates (`templates/`) are server-rendered Jinja with routes doing full-page or redirect-based updates (no SPA/JS framework) — `base.html` is the shared layout with the alerts bell, live-update switch, and screeners nav link; `dashboard.html`/`ticker.html`/`notifications.html`/`screeners.html` extend it.

### Request flow for prices

Ticker prices shown on the dashboard are the *cached* `last_price`/`last_change_pct` columns, refreshed only by the background scheduler — routes never fetch a live quote for display except when adding a new ticker (`symbol_exists` + `fetch_quote` in `add_ticker`) or loading history (`ticker_detail` calls `fetch_history` live, per request, uncached).
