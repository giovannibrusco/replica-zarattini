"""Synthetic bar generators for the tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

ET = "America/New_York"
BARS_PER_DAY = 390  # 09:30 .. 15:59


def make_day(date: str, open_px: float, closes) -> pd.DataFrame:
    """One RTH day of 390 bars. `closes` is a scalar or an array of 390.

    Open of the first bar = open_px (the day's RTH open); high/low = close
    ('flat' bars, so VWAP is the volume-weighted mean of the closes),
    volume 1000.
    """
    idx = pd.date_range(f"{date} 09:30", periods=BARS_PER_DAY, freq="1min", tz=ET)
    closes = np.full(BARS_PER_DAY, closes, dtype=float) if np.isscalar(closes) else np.asarray(closes, dtype=float)
    assert len(closes) == BARS_PER_DAY
    opens = np.concatenate([[open_px], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1000.0,
        },
        index=idx,
    )


def stack_days(*days: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(days).sort_index()


def path_step(before: float, after: float, switch_minute: int) -> np.ndarray:
    """Step path: `before` until the switch minute (exclusive), then `after`.

    switch_minute is the offset in minutes from 09:30 (e.g. 10:00 -> 30).
    """
    path = np.full(BARS_PER_DAY, before, dtype=float)
    path[switch_minute:] = after
    return path
