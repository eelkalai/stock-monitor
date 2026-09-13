import json
import sys

import yfinance as yf


def main():
    try:
        result = yf.screen("day_gainers", count=10)
    except Exception as e:
        print(f"screen() failed: {e}", file=sys.stderr)
        print(json.dumps([]))
        return

    quotes = (result or {}).get("quotes", [])
    output = [
        {
            "symbol": q["symbol"],
            "price": q.get("regularMarketPrice"),
            "change_pct": q.get("regularMarketChangePercent"),
            "note": q.get("shortName") or q.get("longName") or "",
        }
        for q in quotes
        if q.get("symbol")
    ]
    print(json.dumps(output))


if __name__ == "__main__":
    main()
