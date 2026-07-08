"""Download barre 1-minuto da Alpaca Market Data e salvataggio in parquet.

Uso:
    export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...
    python -m src.download_alpaca --symbol SPY --start 2016-01-01 \
        --out data/spy_1min.parquet

Note:
- feed "iex" (free tier): copre ~3% del volume; il VWAP e' approssimato.
  Con abbonamento si puo' passare a --feed sip.
- adjustment "split": prezzi split-adjusted ma non dividend-adjusted, cosi'
  i livelli intraday corrispondono ai prezzi realmente scambiati (la
  strategia e' flat overnight, i dividendi non maturano comunque).
- il download procede per blocchi mensili con retry; alpaca-py gestisce
  la paginazione interna.
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
    """Scarica barre a 1 minuto [start, end) e restituisce OHLCV in tz ET."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    api_key = api_key or os.environ.get("ALPACA_API_KEY")
    secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        sys.exit("Servono ALPACA_API_KEY e ALPACA_SECRET_KEY nell'ambiente.")

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
            except Exception as exc:  # rate limit / rete
                if attempt == max_retries:
                    raise
                wait = 2 ** (attempt + 1)
                print(f"  retry {attempt + 1} tra {wait}s: {exc}", file=sys.stderr)
                _time.sleep(wait)
        if not bars.empty:
            chunk = bars.reset_index(level="symbol", drop=True)
            chunks.append(chunk)
            print(f"  {cur:%Y-%m}: {len(chunk)} barre")
        else:
            print(f"  {cur:%Y-%m}: vuoto")
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
    p.add_argument("--end", default=None, help="default: oggi")
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
        sys.exit("Nessun dato ricevuto.")
    df.to_parquet(out)
    print(f"Salvate {len(df):,} barre in {out}")
    print(f"Range effettivo: {df.index[0]} -> {df.index[-1]}")


if __name__ == "__main__":
    main()
