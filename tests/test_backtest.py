import numpy as np
import pandas as pd
import pytest

from src.backtest import CostModel, run_backtest
from src.sizing import target_units
from .helpers import BARS_PER_DAY, make_day, path_step, stack_days

D = ["2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08"]

O0 = 100.0
O1 = 101.0                 # = day 0 close
O2 = 101.0 * 1.001         # = day 1 close
O3 = O2 * 1.003            # = day 2 close, day 3 open (no gap)

SIGMA_T = 0.002            # mean of the day 1 and day 2 moves (0.001, 0.003)
UPPER = O3 * (1 + SIGMA_T)
LOWER = O3 * (1 - SIGMA_T)
SIGMA_D = np.std([0.001, 0.003], ddof=1)  # daily vol for day 3 sizing

KW = dict(initial_equity=100_000.0, lookback=2, vol_lookback=2)
NO_COSTS = CostModel(commission_per_unit=0.0, min_commission=0.0)


def _history():
    return [
        make_day(D[0], O0, O1),          # move 0.01: outside the sigma window
        make_day(D[1], O1, O2),          # move 0.001
        make_day(D[2], O2, O3),          # move 0.003
    ]


def _run(day3_closes, exit_mode="final", costs=NO_COSTS, **overrides):
    bars = stack_days(*_history(), make_day(D[3], O3, day3_closes))
    return run_backtest(bars, exit_mode=exit_mode, costs=costs, **{**KW, **overrides})


class TestEntriesAndExits:
    def test_no_trade_inside_noise_area(self):
        res = _run(np.full(BARS_PER_DAY, O3))
        assert res.trades.empty
        assert (res.equity == 100_000.0).all()

    def test_breakout_long_held_to_eod(self):
        # breakout at 10:00 (minute 30), then it rises: no re-entry into the area
        path = path_step(O3, 1.005 * O3, 30)
        path[200:] = 1.010 * O3
        res = _run(path)

        assert len(res.trades) == 1
        tr = res.trades.iloc[0]
        assert tr["side"] == "long"
        assert tr["exit_reason"] == "eod"
        assert tr["entry_time"].time() == pd.Timestamp("10:00").time()
        assert tr["exit_time"].time() == pd.Timestamp("15:59").time()

        entry_px = 1.005 * O3
        units = target_units(100_000.0, SIGMA_D, entry_px)
        assert tr["units"] == units
        expected = units * (1.010 * O3 - entry_px)
        assert tr["net_pnl"] == pytest.approx(expected)
        assert res.equity.iloc[-1] == pytest.approx(100_000.0 + expected)

    def test_breakout_short(self):
        path = path_step(O3, 0.995 * O3, 30)
        res = _run(path)
        assert len(res.trades) == 1
        assert res.trades.iloc[0]["side"] == "short"

    def test_entry_before_10am_is_ignored(self):
        # breakout at 09:45 (minute 15) that reverts at 09:55 (minute 25):
        # no check time observes it
        path = np.full(BARS_PER_DAY, O3)
        path[15:25] = 1.01 * O3
        res = _run(path)
        assert res.trades.empty

    def test_late_entry_at_1530_closed_eod(self):
        path = path_step(O3, 1.005 * O3, 360)  # 15:30
        res = _run(path)
        assert len(res.trades) == 1
        tr = res.trades.iloc[0]
        assert tr["entry_time"].time() == pd.Timestamp("15:30").time()
        assert tr["exit_reason"] == "eod"

    def test_missing_check_bar_uses_last_available_price(self):
        # sparse feed: the 10:00 minute is missing; the breakout already
        # happened at 09:59, so the 10:00 check must read the last bar
        # available and enter at 10:00 (not at 10:30)
        path = path_step(O3, 1.005 * O3, 29)  # breakout from 09:59
        day3 = make_day(D[3], O3, path)
        day3 = day3.drop(day3.index[30])  # drops the 10:00 bar
        bars = stack_days(*_history(), day3)
        res = run_backtest(bars, exit_mode="final", costs=NO_COSTS, **KW)
        assert len(res.trades) == 1
        assert res.trades.iloc[0]["entry_time"].time() == pd.Timestamp("10:00").time()

    def test_warmup_days_do_not_trade(self):
        # huge breakout on day 1 (still in warmup: no daily sigma) -> no trade
        bars = stack_days(
            make_day(D[0], O0, O1),
            make_day(D[1], O1, path_step(O1, 1.05 * O1, 30)),
            make_day(D[2], O2, O3),
            make_day(D[3], O3, O3),
        )
        res = run_backtest(bars, exit_mode="final", costs=NO_COSTS, **KW)
        assert res.trades.empty


class TestExitVariants:
    def test_final_exits_on_reentry_base_holds(self):
        # long from 10:00 at 1.005*O3; at 12:00 the price reverts to 1.001*O3
        # (inside the area: below upper but above lower)
        path = path_step(O3, 1.005 * O3, 30)
        path[150:] = 1.001 * O3

        final = _run(path, exit_mode="final")
        assert len(final.trades) == 1
        assert final.trades.iloc[0]["exit_reason"] == "trail"
        assert final.trades.iloc[0]["exit_time"].time() == pd.Timestamp("12:00").time()

        base = _run(path, exit_mode="base")
        assert len(base.trades) == 1
        assert base.trades.iloc[0]["exit_reason"] == "eod"

    def test_base_exits_on_opposite_band(self):
        # long, then a drop below the lower band but without a flip... a drop
        # below lower IS a short signal: the flip is covered by its own test.
        # A pure base exit would need a price between lower and the short
        # signal: impossible (they coincide). A base exit without a flip can
        # therefore only happen via eod. So we verify that base does NOT exit
        # while the price stays above lower.
        path = path_step(O3, 1.005 * O3, 30)
        path[150:] = 0.999 * O3  # above lower (0.998) but inside the area
        base = _run(path, exit_mode="base")
        assert base.trades.iloc[0]["exit_reason"] == "eod"

    def test_short_final_exit_on_reentry(self):
        path = path_step(O3, 0.995 * O3, 30)
        path[150:] = 0.999 * O3  # reverts into the area (above lower)
        final = _run(path, exit_mode="final")
        assert len(final.trades) == 1
        assert final.trades.iloc[0]["side"] == "short"
        assert final.trades.iloc[0]["exit_reason"] == "trail"


class TestFlip:
    def test_long_flips_to_short(self):
        path = path_step(O3, 1.005 * O3, 30)
        path[210:] = 0.995 * O3  # 13:00: below lower -> flip
        res = _run(path)
        assert len(res.trades) == 2
        first, second = res.trades.iloc[0], res.trades.iloc[1]
        assert first["side"] == "long" and first["exit_reason"] == "flip"
        assert first["exit_time"].time() == pd.Timestamp("13:00").time()
        assert second["side"] == "short" and second["exit_reason"] == "eod"
        assert second["entry_time"] == first["exit_time"]


class TestCosts:
    def test_commissions_reduce_pnl(self):
        path = path_step(O3, 1.005 * O3, 30)
        path[200:] = 1.010 * O3
        costs = CostModel(commission_per_unit=0.0035, min_commission=0.35)
        res = _run(path, costs=costs)
        tr = res.trades.iloc[0]
        comm_leg = max(tr["units"] * 0.0035, 0.35)
        assert tr["costs"] == pytest.approx(2 * comm_leg)
        assert tr["net_pnl"] == pytest.approx(tr["gross_pnl"] - 2 * comm_leg)
        assert res.equity.iloc[-1] == pytest.approx(100_000.0 + tr["net_pnl"])

    def test_slippage_applied_to_both_legs(self):
        path = path_step(O3, 1.005 * O3, 30)
        path[200:] = 1.010 * O3
        costs = CostModel(
            commission_per_unit=0.0, min_commission=0.0, slippage_per_unit=0.01
        )
        res = _run(path, costs=costs)
        tr = res.trades.iloc[0]
        assert tr["entry_px"] == pytest.approx(1.005 * O3 + 0.01)  # buys worse
        assert tr["exit_px"] == pytest.approx(1.010 * O3 - 0.01)   # sells worse

    def test_futures_cost_model(self):
        es = CostModel.es_futures(slippage_ticks=0.25)
        assert es.commission(2) == pytest.approx(2 * (0.85 + 1.40))
        assert es.slippage_per_unit == pytest.approx(0.25 * 12.50)


class TestSizing:
    def test_leverage_cap_respected(self):
        path = path_step(O3, 1.005 * O3, 30)
        res = _run(path)
        tr = res.trades.iloc[0]
        notional = tr["units"] * tr["entry_px"]
        assert notional <= 4.0 * 100_000.0
        # with sigma_d ~0.14% the target (1.4M) exceeds the cap: must be near 400k
        assert notional == pytest.approx(400_000.0, rel=0.01)
