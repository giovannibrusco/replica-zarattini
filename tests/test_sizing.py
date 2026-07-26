import numpy as np
import pandas as pd
import pytest

from src.sizing import daily_sigma, target_units


class TestTargetUnits:
    def test_vol_targeting_formula(self):
        # 100k * 2% / 1% = 200k of exposure (below the 400k cap) -> 2000 shares at $100
        assert target_units(100_000, 0.01, 100.0) == 2000

    def test_leverage_cap_binds(self):
        # 100k * 2% / 0.1% = 2M -> capped at 4x = 400k -> 4000 shares at $100
        assert target_units(100_000, 0.001, 100.0) == 4000

    def test_floor(self):
        # 200k / 333 = 600.6 -> 600
        assert target_units(100_000, 0.01, 333.0) == 600

    def test_degenerate_inputs(self):
        assert target_units(100_000, 0.0, 100.0) == 0
        assert target_units(100_000, float("nan"), 100.0) == 0
        assert target_units(0.0, 0.01, 100.0) == 0
        assert target_units(100_000, 0.01, 0.0) == 0

    def test_futures_notional(self):
        # ES: notional = price * 50; 100k*2%/1% = 200k -> floor(200k/250k) = 0
        assert target_units(100_000, 0.01, 5000.0 * 50) == 0
        # with 1M equity: 2M -> 4M cap not binding; 2M/250k = 8 contracts
        assert target_units(1_000_000, 0.01, 5000.0 * 50) == 8


class TestDailySigma:
    def test_no_lookahead_shift(self):
        closes = pd.Series(
            [100.0, 101.0, 100.0, 102.0, 101.0, 103.0],
            index=pd.date_range("2024-02-05", periods=6, freq="B"),
        )
        sig = daily_sigma(closes, lookback=3)
        # first value available: after 3 returns (days 1..3) + shift -> day 4
        assert sig.iloc[:4].isna().all()
        expected = closes.pct_change().iloc[1:4].std()
        assert sig.iloc[4] == pytest.approx(expected)

    def test_matches_manual_std(self):
        rng = np.random.default_rng(42)
        closes = pd.Series(
            100 * np.cumprod(1 + rng.normal(0, 0.01, 30)),
            index=pd.date_range("2024-01-01", periods=30, freq="B"),
        )
        sig = daily_sigma(closes, lookback=14)
        rets = closes.pct_change()
        expected = rets.iloc[15:29].std()  # window ending on day 29-1
        assert sig.iloc[29] == pytest.approx(expected)
