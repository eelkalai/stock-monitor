import json
import math
import sys

import yfinance as yf

TARGET_ANNUAL_GAIN = 0.08


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        hist = yf.Ticker(symbol).history(period="1y")
    except Exception as e:
        print(f"history() failed: {e}", file=sys.stderr)
        print(json.dumps({"recommendation": f"No data available for {symbol}."}))
        return

    closes = [row["Close"] for _, row in hist.iterrows() if not math.isnan(row["Close"])]
    dates = [ts.strftime("%Y-%m-%d") for ts, row in hist.iterrows() if not math.isnan(row["Close"])]

    if len(closes) < 2:
        print(json.dumps({"recommendation": f"No data available for {symbol}."}))
        return

    start_price = closes[0]
    end_price = closes[-1]
    actual_return_pct = (end_price - start_price) / start_price * 100
    target_return_pct = TARGET_ANNUAL_GAIN * 100
    gap_pct = actual_return_pct - target_return_pct

    verdict = "outperforming" if gap_pct >= 0 else "underperforming"
    recommendation = (
        f"{symbol} is {verdict} its {target_return_pct:.0f}% yearly target "
        f"by {abs(gap_pct):.1f} points over the trailing year."
    )
    summary = (
        f"Trailing 1y return: {actual_return_pct:.1f}% "
        f"(${start_price:.2f} -> ${end_price:.2f}), vs a {target_return_pct:.0f}% target."
    )

    # Compound from the start price across the trailing-year sample (i/total_days ~= elapsed years).
    total_days = (len(closes) - 1) or 1
    expected = [
        round(start_price * (1 + TARGET_ANNUAL_GAIN) ** (i / total_days), 2)
        for i in range(len(closes))
    ]

    output = {
        "recommendation": recommendation,
        "summary": summary,
        "metrics": [
            {"label": "Trailing 1y return", "value": f"{actual_return_pct:.1f}%"},
            {"label": "Target annual gain", "value": f"{target_return_pct:.0f}%"},
            {"label": "Start price", "value": f"${start_price:.2f}"},
            {"label": "End price", "value": f"${end_price:.2f}"},
        ],
        "chart": {
            "labels": dates,
            "series": [
                {"label": "Actual", "data": [round(c, 2) for c in closes]},
                {"label": f"Expected ({target_return_pct:.0f}%/yr)", "data": expected},
            ],
        },
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
