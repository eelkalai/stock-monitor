"""Top Gainers"""
import json
import sys

import yfinance as yf

PARAMS = [
    {"name": "count", "label": "Number of results", "type": "number", "default": 10},
]


def main():
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    try:
        count = int(params.get("count") or 10)
    except (TypeError, ValueError):
        count = 10

    try:
        result = yf.screen("day_gainers", count=count)
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
