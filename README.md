# Stock Monitor

A local, single-user Flask web app for tracking a stock watchlist, running custom stock screeners and analyzers, setting price alerts, and tracking a portfolio. Market data comes from Yahoo Finance via [`yfinance`](https://github.com/ranaroussi/yfinance).

## Features

- **Watchlist**: add/remove tickers (validated against Yahoo Finance). Prices refresh in the background every 60s. A topbar switch pauses and resumes this.
- **Charts**: historical price chart per ticker (1mo / 3mo / 6mo / 1y / 5y) with hover readouts.
- **Search**: look up any symbol without adding it to the watchlist. The 10 most recent searches are remembered.
- **Alerts**: one-shot "above"/"below" price thresholds per ticker. When one triggers, it shows up under the bell icon with an unread badge.
- **Screeners**: drop-in Python scripts in `scripts/` that screen any set of symbols. You can give each one parameters, and every run opens its own tab so you can compare results side by side.
- **Analyzers**: drop-in Python scripts in `analyzers/` that take a symbol and return a recommendation, shown in a resizable third pane next to the stock view.
- **Portfolio**: buy and sell any symbol (partial sells are supported). Tracks weighted-average cost basis, realized P&L for closed positions, and a portfolio value-over-time chart.

## Requirements

- Python 3.10+

## Setup

```bash
git clone https://github.com/eelkalai/stock-monitor.git
cd stock-monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python app.py
```

Then open http://127.0.0.1:5000. Set `FLASK_DEBUG=1` to turn on Flask's debug mode.

The background price poller only starts when you run `app.py` directly. It does not start under `flask run` or a WSGI server.

## Writing a screener

Add a file to `scripts/`. Its module docstring becomes the display name. An optional `PARAMS` list declares inputs. Parameters arrive as a JSON object in `sys.argv[1]`, and the script prints a JSON list to stdout:

```python
"""My Screener"""
import json
import sys

PARAMS = [{"name": "count", "label": "Count", "type": "int", "default": 10}]

params = json.loads(sys.argv[1])
print(json.dumps([
    {"symbol": "AAPL", "price": 190.1, "change_pct": 1.2, "note": "example"},
][: params.get("count", 10)]))
```

## Writing an analyzer

Add a file to `analyzers/`. It receives the symbol as `sys.argv[1]` and prints a JSON object with a required `recommendation` string. `summary`, `metrics`, and `chart` are optional. See `analyzers/yearly_performance.py` for an example.

Screeners and analyzers each run in their own subprocess with a timeout, so a broken script can't crash the app.

## Notes

- Data is stored in a local SQLite file, `stock_monitor.db`, created on first run. It is gitignored.
- Yahoo Finance sometimes rate-limits or has short outages. When that happens, the app shows empty data instead of crashing.
- There is no authentication. Run it locally only and don't expose it to a network.

## Disclaimer

This project is for personal and educational use. It is not financial advice.

## License

[MIT](LICENSE)
