"""Test delle estensioni per il protocollo Maroy: griglia check parametrica,
exit 'vwap', deflated Sharpe ratio."""

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
        # breakout visibile solo tra 10:30 e 10:59: la griglia a 60 minuti
        # non lo vede (check a 10:00 e 11:00), quella a 30 si
        path = np.full(BARS_PER_DAY, O3)
        path[60:89] = 1.005 * O3  # 10:30..10:58
        res30 = _run(path)
        res60 = _run(path, check_interval_min=60)
        assert len(res30.trades) == 1
        assert res60.trades.empty

    def test_15min_grid_catches_earlier_entry(self):
        path = path_step(O3, 1.005 * O3, 45)  # breakout alle 10:15
        res15 = _run(path, check_interval_min=15)
        res30 = _run(path)
        assert res15.trades.iloc[0]["entry_time"].time() == pd.Timestamp("10:15").time()
        assert res30.trades.iloc[0]["entry_time"].time() == pd.Timestamp("10:30").time()


class TestVwapExit:
    def test_final_exits_on_band_while_vwap_holds(self):
        # breakout a 10:00 a 1.003*O3, alle 10:30 il prezzo scende a
        # 1.0019*O3: sotto upper (1.002) -> 'final' esce; ma sopra il VWAP
        # (~1.0015 alle 10:30, e resta sotto 1.0019 tutto il giorno perche'
        # trascinato dai 30 minuti iniziali a O3) -> 'vwap' tiene fino a EOD
        path = path_step(O3, 1.003 * O3, 30)
        path[60:] = 1.0019 * O3
        final = _run(path, exit_mode="final")
        vwap = _run(path, exit_mode="vwap")
        assert final.trades.iloc[0]["exit_reason"] == "trail"
        assert final.trades.iloc[0]["exit_time"].time() == pd.Timestamp("10:30").time()
        assert vwap.trades.iloc[0]["exit_reason"] == "eod"

    def test_vwap_exit_triggers_below_vwap(self):
        # prezzo alto a lungo (VWAP sale ~1.005*O3), poi scende sotto il VWAP
        # ma resta sopra lower: 'vwap' esce, 'base' no
        path = path_step(O3, 1.005 * O3, 30)
        path[300:] = 1.000 * O3  # 14:30: sotto il VWAP (~1.0045), sopra lower
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
        r = self._returns(0.003, 0.01)  # SR giornaliero ~0.23
        sr_obs = r.mean() / r.std()
        trials = np.concatenate(
            [np.random.default_rng(2).normal(0, 0.03, 26), [sr_obs]]
        )
        out = deflated_sharpe(r, trials)
        assert out["dsr"] > 0.95

    def test_lucky_winner_fails_deflation(self):
        # vincente con SR pari all'expected max di 27 trial rumorosi: DSR ~0.5
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
