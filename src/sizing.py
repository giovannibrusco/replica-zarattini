"""Position sizing: volatility targeting with a leverage cap.

Formula (spec, FROZEN parameters):
    target_exposure = Equity * vol_target / sigma_daily_lookback
    exposure        = min(target_exposure, max_leverage * Equity)
    units           = floor(exposure / notional_per_unit)

For SPY the unit is 1 share (notional = price); for ES/MES it is one
contract (notional = price * multiplier).
"""

from __future__ import annotations

import math

import pandas as pd

VOL_TARGET = 0.02      # 2% daily — FROZEN
MAX_LEVERAGE = 4.0     # 4x — FROZEN
VOL_LOOKBACK = 14      # days — FROZEN


def daily_sigma(session_close: pd.Series, lookback: int = VOL_LOOKBACK) -> pd.Series:
    """Realised daily vol: std of close-to-close returns over the last
    `lookback` days, available from the next day onwards (shift 1, no
    look-ahead). ddof=1 (pandas default)."""
    rets = session_close.pct_change()
    return rets.rolling(lookback, min_periods=lookback).std().shift(1)


def target_units(
    equity: float,
    sigma_d: float,
    unit_notional: float,
    vol_target: float = VOL_TARGET,
    max_leverage: float = MAX_LEVERAGE,
) -> int:
    """Number of units (shares or contracts) for vol targeting with leverage cap."""
    if not (sigma_d > 0.0) or not (unit_notional > 0.0) or equity <= 0.0:
        return 0
    exposure = min(equity * vol_target / sigma_d, max_leverage * equity)
    return int(math.floor(exposure / unit_notional))
