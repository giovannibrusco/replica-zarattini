"""Smoke test end-to-end: pipeline completa su random walk sintetico."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import CostModel, run_backtest
from src.stats import performance_summary, trade_stats, yearly_table
from .helpers import BARS_PER_DAY, ET, make_day, stack_days


@pytest.fixture(scope="module")
def random_walk_bars():
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-02", periods=40)
    days, price = [], 100.0
    for d in dates:
        # gap overnight + random walk intraday
        open_px = price * (1 + rng.normal(0, 0.003))
        rets = rng.normal(0, 0.0006, BARS_PER_DAY)
        closes = open_px * np.cumprod(1 + rets)
        days.append(make_day(d.strftime("%Y-%m-%d"), open_px, closes))
        price = closes[-1]
    return stack_days(*days)


def test_full_pipeline_runs(random_walk_bars):
    results = {}
    for mode in ("base", "final"):
        res = run_backtest(
            random_walk_bars,
            exit_mode=mode,
            costs=CostModel(),
        )
        assert not res.trades.empty, f"nessun trade in modalita' {mode}"
        # contabilita': equity finale = iniziale + somma dei net pnl
        assert res.equity.iloc[-1] == pytest.approx(
            100_000.0 + res.trades["net_pnl"].sum()
        )
        # sempre flat overnight: ogni trade apre e chiude lo stesso giorno
        same_day = (
            res.trades["entry_time"].dt.normalize()
            == res.trades["exit_time"].dt.normalize()
        )
        assert same_day.all()
        # nessun trade nei giorni di warmup (14 gg sigma + 15 gg vol daily)
        first_trade_day = res.trades["entry_time"].min().normalize()
        warmup_end = random_walk_bars.index.normalize().unique()[14]
        assert first_trade_day >= warmup_end
        results[mode] = res

    # la variante final esce prima o uguale: mai piu' tardi della base
    # (stesso entry -> exit final <= exit base per costruzione del trailing)
    perf = performance_summary(results["final"].daily_returns)
    tstats = trade_stats(results["final"].trades)
    assert np.isfinite(perf["sharpe"])
    assert 0.0 <= tstats["win_rate"] <= 1.0
    assert tstats["n_trades"] == len(results["final"].trades)

    yt = yearly_table(results["final"].daily_returns)
    assert len(yt) == 1  # un solo anno nel campione sintetico


def test_final_never_exits_later_than_base(random_walk_bars):
    """A parita' di entry, il trailing 'final' e' piu' stretto del 'base'."""
    base = run_backtest(random_walk_bars, exit_mode="base", costs=CostModel())
    final = run_backtest(random_walk_bars, exit_mode="final", costs=CostModel())
    b = base.trades.set_index("entry_time")["exit_time"]
    f = final.trades.set_index("entry_time")["exit_time"]
    common = b.index.intersection(f.index)
    assert len(common) > 0
    assert (f.loc[common] <= b.loc[common]).all()
