import numpy as np
import pandas as pd
import pytest

from src.noise_area import build_indicators, compute_sigma, compute_vwap
from .helpers import make_day, stack_days

# consecutive trading days (Feb 2024, no holidays)
DATES = [
    "2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09",
    "2024-02-12", "2024-02-13", "2024-02-14", "2024-02-15", "2024-02-16",
    "2024-02-20", "2024-02-21", "2024-02-22", "2024-02-23", "2024-02-26",
    "2024-02-27", "2024-02-28",
]


def _constant_move_days(moves: list[float], start_open: float = 100.0):
    """Days where every bar has |close/day_open - 1| = a constant move,
    concatenated without gaps (day open = previous day's close)."""
    days, o = [], start_open
    for date, m in zip(DATES, moves):
        c = o * (1.0 + m)
        days.append(make_day(date, o, c))
        o = c
    return stack_days(*days)


class TestSigma:
    def test_mean_over_lookback_excludes_current_day(self):
        # 15 days: move of day i = 0.001*(i+1)
        moves = [0.001 * (i + 1) for i in range(15)]
        df = _constant_move_days(moves)
        sigma = compute_sigma(df, lookback=14, min_obs=14)

        # on day 15 (index 14): mean of the day 0..13 moves; the current
        # day's move (0.015) must NOT be included
        day15 = sigma[sigma.index.normalize() == sigma.index.normalize().unique()[14]]
        expected = np.mean(moves[:14])
        assert day15.notna().all()
        np.testing.assert_allclose(day15.to_numpy(), expected, rtol=1e-12)

    def test_warmup_is_nan(self):
        moves = [0.001] * 15
        df = _constant_move_days(moves)
        sigma = compute_sigma(df, lookback=14, min_obs=14)
        days = sigma.index.normalize()
        uniq = days.unique()
        for d in uniq[:14]:
            assert sigma[days == d].isna().all(), f"day {d} should have been warmup"
        assert sigma[days == uniq[14]].notna().all()

    def test_rolling_window_drops_old_days(self):
        # lookback=2: on day 3 sigma = mean(day 1 move, day 2 move);
        # day 0's huge move must be outside the window
        moves = [0.050, 0.001, 0.003, 0.002]
        df = _constant_move_days(moves)
        sigma = compute_sigma(df, lookback=2, min_obs=2)
        days = sigma.index.normalize()
        day3 = sigma[days == days.unique()[3]]
        np.testing.assert_allclose(day3.to_numpy(), 0.002, rtol=1e-12)


class TestBands:
    def test_gap_up_anchoring(self):
        # 2 "historical" days with moves 0.001 and 0.003 (sigma=0.002), then a
        # gap up: prev close 100.4003, open 105 -> upper anchored to 105,
        # lower to the previous close
        d0 = make_day(DATES[0], 100.0, 100.1)
        d1 = make_day(DATES[1], 100.1, 100.1 * 1.003)
        prev_close = 100.1 * 1.003
        d2 = make_day(DATES[2], 105.0, 105.5)
        ind = build_indicators(stack_days(d0, d1, d2), lookback=2, min_obs=2)

        day3 = ind[ind.index.normalize() == ind.index.normalize().unique()[2]]
        sigma = 0.002
        np.testing.assert_allclose(day3["upper"].to_numpy(), 105.0 * (1 + sigma), rtol=1e-12)
        np.testing.assert_allclose(day3["lower"].to_numpy(), prev_close * (1 - sigma), rtol=1e-12)

    def test_gap_down_anchoring(self):
        d0 = make_day(DATES[0], 100.0, 100.1)
        d1 = make_day(DATES[1], 100.1, 100.1 * 1.003)
        prev_close = 100.1 * 1.003
        d2 = make_day(DATES[2], 95.0, 95.2)  # gap down
        ind = build_indicators(stack_days(d0, d1, d2), lookback=2, min_obs=2)

        day3 = ind[ind.index.normalize() == ind.index.normalize().unique()[2]]
        sigma = 0.002
        np.testing.assert_allclose(day3["upper"].to_numpy(), prev_close * (1 + sigma), rtol=1e-12)
        np.testing.assert_allclose(day3["lower"].to_numpy(), 95.0 * (1 - sigma), rtol=1e-12)

    def test_no_gap_bands_around_open(self):
        d0 = make_day(DATES[0], 100.0, 100.1)
        d1 = make_day(DATES[1], 100.1, 100.1 * 1.003)
        prev_close = 100.1 * 1.003
        d2 = make_day(DATES[2], prev_close, prev_close * 1.001)  # no gap
        ind = build_indicators(stack_days(d0, d1, d2), lookback=2, min_obs=2)

        day3 = ind[ind.index.normalize() == ind.index.normalize().unique()[2]]
        sigma = 0.002
        np.testing.assert_allclose(day3["upper"].to_numpy(), prev_close * (1 + sigma), rtol=1e-12)
        np.testing.assert_allclose(day3["lower"].to_numpy(), prev_close * (1 - sigma), rtol=1e-12)


class TestVwap:
    def test_session_vwap_typical_price(self):
        df = make_day(DATES[0], 100.0, 100.0).iloc[:3].copy()
        df["high"] = [101.0, 102.0, 103.0]
        df["low"] = [99.0, 100.0, 101.0]
        df["close"] = [100.0, 101.0, 102.0]
        df["volume"] = [1000.0, 2000.0, 3000.0]
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = compute_vwap(df)
        expected_last = (tp * df["volume"]).sum() / df["volume"].sum()
        assert vwap.iloc[0] == pytest.approx(tp.iloc[0])
        assert vwap.iloc[-1] == pytest.approx(expected_last)

    def test_vwap_resets_each_day(self):
        d0 = make_day(DATES[0], 100.0, 100.0)
        d1 = make_day(DATES[1], 200.0, 200.0)
        vwap = compute_vwap(stack_days(d0, d1))
        days = vwap.index.normalize()
        np.testing.assert_allclose(vwap[days == days.unique()[0]].to_numpy(), 100.0)
        np.testing.assert_allclose(vwap[days == days.unique()[1]].to_numpy(), 200.0)


class TestIndicators:
    def test_day_open_and_prev_close_columns(self):
        d0 = make_day(DATES[0], 100.0, 100.5)
        d1 = make_day(DATES[1], 101.0, 101.2)
        ind = build_indicators(stack_days(d0, d1), lookback=2, min_obs=1)
        days = ind.index.normalize()
        day2 = ind[days == days.unique()[1]]
        assert (day2["day_open"] == 101.0).all()
        assert (day2["prev_close"] == 100.5).all()
        day1 = ind[days == days.unique()[0]]
        assert day1["prev_close"].isna().all()

    def test_requires_tz_aware(self):
        df = make_day(DATES[0], 100.0, 100.0)
        df.index = df.index.tz_localize(None)
        with pytest.raises(ValueError):
            build_indicators(df)
