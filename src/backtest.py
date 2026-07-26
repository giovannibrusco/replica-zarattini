"""Event-driven backtest engine for the Noise Area strategy.

Rules (spec):
- Entry/exit checks ONLY on the 30-minute timestamps: 10:00, 10:30, ..., 15:30.
  The price used is the close of the 1-minute bar labelled at the check time.
- Entry: price > Upper_t -> LONG; price < Lower_t -> SHORT. Flips allowed.
- Exit variant "base":   a long exits if price < Lower_t (opposite band);
                         a short exits if price > Upper_t.
- Exit variant "final":  a long exits if price < max(VWAP_t, Upper_t);
                         a short exits if price > min(VWAP_t, Lower_t)
  (re-entry into the Noise Area, or a cross of the session VWAP).
- Everything is force-closed on the last RTH bar (15:59, session close
  price): zero overnight exposure.
- Sizing: 2% vol targeting with a 4x leverage cap, computed at entry on
  current equity (compounding).

Costs (parametric, see CostModel): for shares, commission per share plus
slippage in dollars per share; for futures, commission+fees per contract
plus slippage in ticks. Charged per transaction (entry and exit separately).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

from .noise_area import build_indicators, session_closes, _day_key
from .sizing import (
    MAX_LEVERAGE,
    VOL_LOOKBACK,
    VOL_TARGET,
    daily_sigma,
    target_units,
)

def check_times(interval_min: int = 30) -> list[time]:
    """Check grid: from 10:00 every `interval_min` minutes, last one <= 15:45.

    30 minutes (10:00 ... 15:30) is the paper's value, FROZEN for the
    replication; other intervals are allowed ONLY in the Maroy protocol.
    """
    out, minutes = [], 10 * 60
    while minutes <= 15 * 60 + 45:
        out.append(time(minutes // 60, minutes % 60))
        minutes += interval_min
    return out


# the paper's grid: 10:00, 10:30, ..., 15:30
CHECK_TIMES = check_times(30)
FORCED_EXIT_TIME = time(15, 59)


@dataclass
class CostModel:
    """Costs per transaction (one leg; a round trip = two transactions)."""

    commission_per_unit: float = 0.0035  # $/share (IB, as in the paper) or $/contract
    fees_per_unit: float = 0.0           # exchange+regulatory (futures)
    slippage_per_unit: float = 0.0       # $ per unit per transaction
    min_commission: float = 0.35         # per-order minimum (IB stocks)

    def commission(self, units: int) -> float:
        return max(self.commission_per_unit * units, self.min_commission) + (
            self.fees_per_unit * units
        )

    @staticmethod
    def es_futures(slippage_ticks: float = 0.25, micro: bool = False) -> "CostModel":
        """Spec costs for ES/MES: commission+fees per contract, slippage in ticks."""
        tick_value = 1.25 if micro else 12.50  # 0.25 index points
        return CostModel(
            commission_per_unit=0.25 if micro else 0.85,
            fees_per_unit=0.35 if micro else 1.40,
            slippage_per_unit=slippage_ticks * tick_value,
            min_commission=0.0,
        )


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series          # end-of-day equity (always flat overnight)
    daily_returns: pd.Series = field(init=False)

    def __post_init__(self) -> None:
        self.daily_returns = self.equity.pct_change().fillna(0.0)


def run_backtest(
    bars: pd.DataFrame,
    initial_equity: float = 100_000.0,
    exit_mode: str = "final",
    costs: CostModel | None = None,
    unit_multiplier: float = 1.0,  # 1 for shares; 50 for ES, 5 for MES
    lookback: int = 14,
    vol_target: float = VOL_TARGET,
    max_leverage: float = MAX_LEVERAGE,
    vol_lookback: int = VOL_LOOKBACK,
    check_interval_min: int = 30,
) -> BacktestResult:
    """Run the backtest on 1-minute RTH bars (see noise_area for the format).

    exit_mode: "base" (opposite band), "final" (max/min of VWAP and the entry
    band, the paper's variant) or "vwap" (VWAP only, Maroy variant).
    """
    if exit_mode not in ("base", "final", "vwap"):
        raise ValueError("exit_mode must be 'base', 'final' or 'vwap'")
    if costs is None:
        costs = CostModel()

    ind = build_indicators(bars, lookback=lookback)
    closes_d = session_closes(ind)
    sigma_d = daily_sigma(closes_d, lookback=vol_lookback)

    equity = initial_equity
    trades: list[dict] = []
    equity_by_day: dict[pd.Timestamp, float] = {}

    # current position
    side = 0  # +1 long, -1 short, 0 flat
    units = 0
    entry_px = 0.0
    entry_time = None

    def _exec_price(px: float, buy: bool) -> float:
        slip = costs.slippage_per_unit / unit_multiplier
        return px + slip if buy else px - slip

    def _close_position(px: float, ts: pd.Timestamp, reason: str) -> None:
        nonlocal equity, side, units, entry_px, entry_time
        exec_px = _exec_price(px, buy=(side < 0))
        gross = side * units * (exec_px - entry_px) * unit_multiplier
        comm = costs.commission(units)
        equity += gross - comm
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": ts,
                "side": "long" if side > 0 else "short",
                "units": units,
                "entry_px": entry_px,
                "exit_px": exec_px,
                "gross_pnl": gross,
                "costs": comm + trades_open_cost[0],
                "net_pnl": gross - comm - trades_open_cost[0],
                "exit_reason": reason,
                "equity_after": equity,
            }
        )
        side, units, entry_px, entry_time = 0, 0, 0.0, None

    def _open_position(new_side: int, px: float, ts: pd.Timestamp, sd: float) -> None:
        nonlocal equity, side, units, entry_px, entry_time
        exec_px = _exec_price(px, buy=(new_side > 0))
        n = target_units(
            equity, sd, exec_px * unit_multiplier, vol_target, max_leverage
        )
        if n <= 0:
            return
        comm = costs.commission(n)
        equity -= comm
        trades_open_cost[0] = comm
        side, units, entry_px, entry_time = new_side, n, exec_px, ts

    trades_open_cost = [0.0]  # opening cost of the current trade

    grid = check_times(check_interval_min)

    for day, day_bars in ind.groupby(_day_key(ind.index)):
        sd = sigma_d.get(day, np.nan)
        times = day_bars.index.time

        for t in grid:
            # last bar available <= check time: if the exact minute is
            # missing (sparse feed) the last traded price is used
            pos = np.searchsorted(times, t, side="right") - 1
            if pos < 0:
                continue
            row = day_bars.iloc[pos]
            px, upper, lower, vwap = (
                row["close"], row["upper"], row["lower"], row["vwap"]
            )
            if not np.isfinite(upper) or not np.isfinite(lower):
                continue  # warmup or insufficient data: do not trade
            ts = pd.Timestamp.combine(day.date(), t).tz_localize(day_bars.index.tz)

            long_sig = px > upper
            short_sig = px < lower

            if side > 0:
                long_trail = (
                    lower if exit_mode == "base"
                    else max(vwap, upper) if exit_mode == "final"
                    else vwap
                )
                if short_sig:  # flip long -> short
                    _close_position(px, ts, "flip")
                    if np.isfinite(sd):
                        _open_position(-1, px, ts, sd)
                elif px < long_trail:
                    _close_position(px, ts, "trail")
            elif side < 0:
                short_trail = (
                    upper if exit_mode == "base"
                    else min(vwap, lower) if exit_mode == "final"
                    else vwap
                )
                if long_sig:  # flip short -> long
                    _close_position(px, ts, "flip")
                    if np.isfinite(sd):
                        _open_position(1, px, ts, sd)
                elif px > short_trail:
                    _close_position(px, ts, "trail")
            else:
                if (long_sig or short_sig) and np.isfinite(sd):
                    _open_position(1 if long_sig else -1, px, ts, sd)

        # forced close at the end of the session (zero overnight)
        if side != 0:
            last = day_bars.iloc[-1]
            ts = day_bars.index[-1]
            _close_position(last["close"], ts, "eod")

        equity_by_day[day] = equity

    trades_df = pd.DataFrame(trades)
    equity_series = pd.Series(equity_by_day, name="equity").sort_index()
    return BacktestResult(trades=trades_df, equity=equity_series)
