"""Tests for the Maroy-protocol extensions: parametric check grid,
'vwap' exit, deflated Sharpe ratio."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import check_times, run_backtest
from src.stats import deflated_sharpe
from .test_backtest import KW, NO_COSTS, O3, _history, _run
from .helpers import BARS_PER_DAY, make_day, path_step, stack_days


class TestCheckTimes:
    def test_paper_grid_30min(self):
        grid = check_times(30)
        assert grid[0] == pd.Timestamp("10:00").time()
        assert grid[-1] == pd.Timestamp("15:30").time()
        assert len(grid) == 12

    def test_15min_grid_ends_1545(self):
        grid = check_times(15)
        assert grid[-1] == pd.Timestamp("15:45").time()
        assert len(grid) == 24

    def test_60min_grid_ends_1500(self):
        grid = check_times(60)
        assert grid[-1] == pd.Timestamp("15:00").time()
        assert len(grid) == 6


class TestIntervalParam:
    def test_60min_grid_skips_1030_signal(self):
        # breakout visible only between 10:30 and 10:59: the 60-minute grid
        # misses it (checks at 10:00 and 11:00), the 30-minute one sees it
        path = np.full(BARS_PER_DAY, O3)
        path[60:89] = 1.005 * O3  # 10:30..10:58
        res30 = _run(path)
        res60 = _run(path, check_interval_min=60)
        assert len(res30.trades) == 1
        assert res60.trades.empty

    def test_15min_grid_catches_earlier_entry(self):
        path = path_step(O3, 1.005 * O3, 45)  # breakout at 10:15
        res15 = _run(path, check_interval_min=15)
        res30 = _run(path)
        assert res15.trades.iloc[0]["entry_time"].time() == pd.Timestamp("10:15").time()
        assert res30.trades.iloc[0]["entry_time"].time() == pd.Timestamp("10:30").time()


class TestVwapExit:
    def test_final_exits_on_band_while_vwap_holds(self):
        # breakout at 10:00 to 1.003*O3; at 10:30 the price falls to
        # 1.0019*O3: below upper (1.002) -> 'final' exits; but above VWAP
        # (~1.0015 at 10:30, and it stays below 1.0019 all day because it is
        # dragged down by the first 30 minutes at O3) -> 'vwap' holds to EOD
        path = path_step(O3, 1.003 * O3, 30)
        path[60:] = 1.0019 * O3
        final = _run(path, exit_mode="final")
        vwap = _run(path, exit_mode="vwap")
        assert final.trades.iloc[0]["exit_reason"] == "trail"
        assert final.trades.iloc[0]["exit_time"].time() == pd.Timestamp("10:30").time()
        assert vwap.trades.iloc[0]["exit_reason"] == "eod"

    def test_vwap_exit_triggers_below_vwap(self):
        # price high for a long time (VWAP rises to ~1.005*O3), then it falls
        # below VWAP but stays above lower: 'vwap' exits, 'base' does not
        path = path_step(O3, 1.005 * O3, 30)
        path[300:] = 1.000 * O3  # 14:30: below VWAP (~1.0045), above lower
        vwap = _run(path, exit_mode="vwap")
        base = _run(path, exit_mode="base")
        assert vwap.trades.iloc[0]["exit_reason"] == "trail"
        assert vwap.trades.iloc[0]["exit_time"].time() == pd.Timestamp("14:30").time()
        assert base.trades.iloc[0]["exit_reason"] == "eod"


class TestDeflatedSharpe:
    def _returns(self, mean, std, n=800, seed=1):
        rng = np.random.default_rng(seed)
        return pd.Series(
            rng.normal(mean, std, n),
            index=pd.bdate_range("2021-01-01", periods=n),
        )

    def test_strong_signal_survives_deflation(self):
        r = self._returns(0.003, 0.01)  # daily SR ~0.23
        sr_obs = r.mean() / r.std()
        trials = np.concatenate(
            [np.random.default_rng(2).normal(0, 0.03, 26), [sr_obs]]
        )
        out = deflated_sharpe(r, trials)
        assert out["dsr"] > 0.95

    def test_lucky_winner_fails_deflation(self):
        # a winner with SR equal to the expected max of 27 noisy trials: DSR ~0.5
        rng = np.random.default_rng(3)
        trials = rng.normal(0, 0.05, 27)
        sr_win = trials.max()
        r = self._returns(sr_win * 0.01, 0.01, seed=4)  # SR ~ sr_win
        out = deflated_sharpe(r, trials)
        assert out["dsr"] < 0.95

    def test_more_trials_raise_threshold(self):
        r = self._returns(0.001, 0.01)
        few = deflated_sharpe(r, list(np.linspace(-0.05, 0.1, 5)))
        many = deflated_sharpe(r, list(np.linspace(-0.05, 0.1, 100)))
        assert many["sr0_daily"] > few["sr0_daily"]
        assert many["dsr"] < few["dsr"]
