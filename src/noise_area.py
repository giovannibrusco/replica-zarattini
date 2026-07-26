"""Noise Area: sigma_t, bands and session VWAP.

Replication of Zarattini, Aziz, Barbon (2024) "Beat the Market".

Input data conventions:
- DataFrame of 1-minute bars with a tz-aware DatetimeIndex (America/New_York)
- columns: open, high, low, close, volume
- RTH session only: bars labelled 09:30 through 15:59 inclusive (the bar
  labelled HH:MM covers [HH:MM, HH:MM+1))

Definitions (spec):
    sigma_t   = mean over the last `lookback` days of |P_{d,t} / O_d - 1|
                (the current day is ALWAYS excluded)
    Upper_t   = max(O_D, C_{D-1}) * (1 + sigma_t)
    Lower_t   = min(O_D, C_{D-1}) * (1 - sigma_t)
    VWAP_t    = session VWAP from 09:30, typical price (H+L+C)/3

Anchoring to max/min(Open, previous Close) handles overnight gaps: with a
gap the Noise Area widens until it covers both reference levels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RTH_START = "09:30"
RTH_LAST_BAR = "15:59"  # last 1-minute bar of the RTH session

DEFAULT_LOOKBACK = 14  # days — parameter FROZEN by spec, do not optimise


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep RTH bars only (labels 09:30..15:59)."""
    if df.index.tz is None:
        raise ValueError("index must be tz-aware (America/New_York)")
    return df.between_time(RTH_START, RTH_LAST_BAR)


def _day_key(index: pd.DatetimeIndex) -> pd.Index:
    return index.normalize()


def session_opens(df: pd.DataFrame) -> pd.Series:
    """RTH open of each day (open of the session's first bar)."""
    return df["open"].groupby(_day_key(df.index)).first()


def session_closes(df: pd.DataFrame) -> pd.Series:
    """RTH close of each day (close of the session's last bar)."""
    return df["close"].groupby(_day_key(df.index)).last()


def compute_sigma(
    df: pd.DataFrame,
    lookback: int = DEFAULT_LOOKBACK,
    min_obs: int | None = None,
) -> pd.Series:
    """sigma_t for each bar: `lookback`-day mean of |P_{d,t}/O_d - 1|.

    The current day is excluded (shifted by one day). To handle half
    sessions (early closes) where some minutes are missing, the mean
    requires at least `min_obs` observations available in the window
    (default: lookback // 2); below that threshold sigma_t is NaN and the
    backtest does not trade at that minute.
    """
    if min_obs is None:
        min_obs = max(1, lookback // 2)

    days = _day_key(df.index)
    opens = session_opens(df).reindex(days)
    opens.index = df.index
    move = (df["close"] / opens - 1.0).abs()

    # days x minute-of-session matrix
    frame = pd.DataFrame(
        {"day": days, "tod": df.index.time, "move": move.to_numpy()}
    )
    pivot = frame.pivot(index="day", columns="tod", values="move")

    sigma_by_day = (
        pivot.rolling(lookback, min_periods=min_obs).mean().shift(1)
    )

    # back to long form, aligned with the original bars
    long = sigma_by_day.stack(future_stack=True).rename("sigma")
    keys = pd.MultiIndex.from_arrays([days, df.index.time])
    out = pd.Series(long.reindex(keys).to_numpy(), index=df.index, name="sigma")
    return out


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP from 09:30, using typical price (H+L+C)/3."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    days = _day_key(df.index)
    pv = (tp * df["volume"]).groupby(days).cumsum()
    v = df["volume"].groupby(days).cumsum()
    vwap = pv / v
    vwap.name = "vwap"
    return vwap


def build_indicators(
    df: pd.DataFrame,
    lookback: int = DEFAULT_LOOKBACK,
    min_obs: int | None = None,
) -> pd.DataFrame:
    """DataFrame enriched with sigma, bands, vwap, day open and previous close.

    Rows in the first `lookback` days have NaN sigma/bands (warmup).
    """
    df = filter_rth(df).sort_index()
    days = _day_key(df.index)

    opens = session_opens(df)
    closes = session_closes(df)
    prev_close = closes.shift(1)

    upper_anchor = np.maximum(opens, prev_close)
    lower_anchor = np.minimum(opens, prev_close)

    out = df.copy()
    out["day_open"] = opens.reindex(days).to_numpy()
    out["prev_close"] = prev_close.reindex(days).to_numpy()
    out["sigma"] = compute_sigma(df, lookback=lookback, min_obs=min_obs)
    out["upper"] = upper_anchor.reindex(days).to_numpy() * (1.0 + out["sigma"])
    out["lower"] = lower_anchor.reindex(days).to_numpy() * (1.0 - out["sigma"])
    out["vwap"] = compute_vwap(df)
    return out
