# Stock Monitor

A local Flask web app for tracking a stock watchlist, viewing historical charts, and setting in-app price alerts. Market data comes from Yahoo Finance via `yfinance`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python app.py
```

Then open http://127.0.0.1:5000

## Features

- Add/remove tickers to a watchlist; prices refresh automatically every 60s in the background.
- Click a ticker to see a historical price chart (1mo/3mo/6mo/1y/5y).
- Set "above"/"below" price alerts per ticker; triggered alerts appear under the "Alerts" bell in the top bar with an unread badge.

## Notes

Data is stored in a local SQLite file (`stock_monitor.db`, gitignored). Yahoo Finance occasionally rate-limits or has transient outages — the app degrades gracefully (shows an error instead of crashing) when a quote can't be fetched.
