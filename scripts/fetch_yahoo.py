#!/usr/bin/env python3
"""Fetch recent price data from Yahoo Finance and merge into docs/data/*.js files.
Temporary fallback when Stooq is unavailable."""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"

# Yahoo Finance symbol -> (JS variable name, output filename)
SYMBOLS = {
    "^GSPC":   ("SP500_DATA",     "sp500.js"),
    "^NDX":    ("NASDAQ100_DATA", "nasdaq100.js"),
    "^DJI":    ("DOWJONES_DATA",  "dowjones.js"),
    "VTI":     ("VTI_DATA",       "vti.js"),
    "^N225":   ("NIKKEI225_DATA", "nikkei225.js"),
    "GC=F":    ("GOLD_DATA",      "gold.js"),
}

def fetch_yahoo(symbol: str, start_ts: int, end_ts: int) -> list[tuple[str, float]]:
    """Fetch daily close prices from Yahoo Finance."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]

            rows = []
            for ts, close in zip(timestamps, closes):
                if close is None:
                    continue
                date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                rows.append((date_str, round(close, 2)))
            return rows
        except Exception as e:
            if attempt == 3:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  Retry {attempt+1} for {symbol} in {wait}s: {e}")
            time.sleep(wait)


def read_existing(filepath: Path) -> list[tuple[str, float]]:
    """Parse existing JS data file to extract date/price pairs."""
    if not filepath.exists():
        return []
    text = filepath.read_text()
    start = text.find("[[")
    end = text.rfind("]]")
    if start == -1 or end == -1:
        return []
    inner = text[start + 1 : end + 1]
    rows = []
    for chunk in inner.split("],["):
        chunk = chunk.strip("[]")
        parts = chunk.split(",", 1)
        if len(parts) == 2:
            date = parts[0].strip('"')
            try:
                price = float(parts[1])
                rows.append((date, price))
            except ValueError:
                continue
    return rows


def write_js(filepath: Path, var_name: str, rows: list[tuple[str, float]]) -> None:
    """Write data as a single-line JS const."""
    pairs = ",".join(f'["{d}",{p}]' for d, p in rows)
    filepath.write_text(f"const {var_name} = [{pairs}];\n")


def main():
    # Fetch from day after last data point to today
    start_date = datetime(2026, 3, 7)
    end_date = datetime.now()

    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())

    updated = []

    for symbol, (var_name, filename) in SYMBOLS.items():
        filepath = DOCS_DATA / filename
        print(f"Fetching {symbol} -> {filename} ...")

        existing = read_existing(filepath)
        existing_dates = {d for d, _ in existing}

        try:
            fetched = fetch_yahoo(symbol, start_ts, end_ts)
        except Exception as e:
            print(f"  ERROR: Failed to fetch {symbol}: {e}")
            continue

        if not fetched:
            print(f"  No new data for {symbol}.")
            continue

        new_rows = [(d, p) for d, p in fetched if d not in existing_dates]

        if not new_rows:
            print(f"  No new data for {symbol} (all dates already exist).")
            continue

        merged = existing + new_rows
        merged.sort(key=lambda r: r[0])

        write_js(filepath, var_name, merged)
        print(f"  Updated {filename}: +{len(new_rows)} new (total {len(merged)}, latest: {merged[-1][0]}).")
        updated.append(filename)

        time.sleep(1)

    if updated:
        print(f"\nUpdated files: {', '.join(updated)}")
    else:
        print("\nNo updates needed.")

    sys.exit(0 if updated else 1)


if __name__ == "__main__":
    main()
