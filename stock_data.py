import math

import yfinance as yf


def fetch_quote(symbol):
    """Return (price, change_pct) for a symbol, or (None, None) if unavailable."""
    try:
        hist = yf.Ticker(symbol).history(period="5d")
    except Exception:
        return None, None

    if hist.empty:
        return None, None

    price = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
    change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0.0
    return price, change_pct


def symbol_exists(symbol):
    price, _ = fetch_quote(symbol)
    return price is not None


def fetch_history(symbol, period="6mo", interval="1d"):
    try:
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
    except Exception:
        return []

    return [
        {
            "date": ts.strftime("%Y-%m-%d"),
            "close": None if math.isnan(row["Close"]) else round(row["Close"], 2),
        }
        for ts, row in hist.iterrows()
    ]
