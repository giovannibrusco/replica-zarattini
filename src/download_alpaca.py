"""Download 1-minute bars from Alpaca Market Data and store them as parquet.

Usage:
    export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...
    python -m src.download_alpaca --symbol SPY --start 2016-01-01 \
        --out data/spy_1min.parquet

Notes:
- the "iex" feed (free tier) covers ~3% of consolidated volume, so VWAP is
  approximated. With a subscription you can switch to --feed sip.
- the free tier only serves roughly the last ~6 years, so an earlier
  --start silently yields a later first bar; check the printed range.
- adjustment "split": prices are split-adjusted but not dividend-adjusted,
  so intraday levels match actually traded prices (the strategy is flat
  overnight, so dividends do not accrue anyway).
- the download runs in monthly chunks with retries; alpaca-py handles
  pagination internally.
"""

from __future__ import annotations

import argparse
import os
import sys
import time as _time
from datetime import datetime, timedelta, timezone

import pandas as pd

ET = "America/New_York"


def fetch_minute_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    feed: str = "iex",
    api_key: str | None = None,
    secret_key: str | None = None,
    max_retries: int = 4,
) -> pd.DataFrame:
    """Download 1-minute bars over [start, end) and return OHLCV in ET."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    api_key = api_key or os.environ.get("ALPACA_API_KEY")
    secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        sys.exit("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in the environment.")

    client = StockHistoricalDataClient(api_key, secret_key)

    chunks: list[pd.DataFrame] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=31), end)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=cur,
            end=nxt,
            feed=feed,
            adjustment="split",
        )
        for attempt in range(max_retries + 1):
            try:
                bars = client.get_stock_bars(req).df
                break
            except Exception as exc:  # rate limit / network
                if attempt == max_retries:
                    raise
                wait = 2 ** (attempt + 1)
                print(f"  retry {attempt + 1} in {wait}s: {exc}", file=sys.stderr)
                _time.sleep(wait)
        if not bars.empty:
            chunk = bars.reset_index(level="symbol", drop=True)
            chunks.append(chunk)
            print(f"  {cur:%Y-%m}: {len(chunk)} bars")
        else:
            print(f"  {cur:%Y-%m}: empty")
        cur = nxt

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.index = df.index.tz_convert(ET)
    return df[["open", "high", "low", "close", "volume"]]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--start", default="2016-01-01")
    p.add_argument("--end", default=None, help="default: today")
    p.add_argument("--feed", default="iex", choices=["iex", "sip"])
    p.add_argument("--out", default=None, help="default: data/<symbol>_1min.parquet")
    args = p.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end
        else datetime.now(timezone.utc)
    )
    out = args.out or f"data/{args.symbol.lower()}_1min.parquet"

    print(f"Download {args.symbol} 1-min [{start:%Y-%m-%d} -> {end:%Y-%m-%d}] feed={args.feed}")
    df = fetch_minute_bars(args.symbol, start, end, feed=args.feed)
    if df.empty:
        sys.exit("No data received.")
    df.to_parquet(out)
    print(f"Saved {len(df):,} bars to {out}")
    print(f"Actual range: {df.index[0]} -> {df.index[-1]}")


if __name__ == "__main__":
    main()
