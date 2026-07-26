"""Stitching tests (volume-crossover roll + additive back-adjustment)."""

import pandas as pd

from src.download_ib import quarterly_expiries, stitch


def _mk(days_px_vol):
    frames = []
    for d, px, vol in days_px_vol:
        i = pd.date_range(f"{d} 09:30", periods=390, freq="1min",
                          tz="America/New_York")
        frames.append(pd.DataFrame(
            {"open": px, "high": px, "low": px, "close": px, "volume": vol},
            index=i,
        ))
    return pd.concat(frames)


DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]


def _two_contracts():
    front = _mk([(DAYS[0], 100.0, 10), (DAYS[1], 101.0, 10),
                 (DAYS[2], 102.0, 10), (DAYS[3], 103.0, 4), (DAYS[4], 104.0, 2)])
    nxt = _mk([(DAYS[1], 111.5, 1), (DAYS[2], 112.5, 3),
               (DAYS[3], 113.0, 8), (DAYS[4], 114.0, 12)])
    return [
        ("ESH6", pd.Timestamp("2026-03-20", tz="UTC"), front),
        ("ESM6", pd.Timestamp("2026-06-19", tz="UTC"), nxt),
    ]


class TestStitch:
    def test_roll_at_volume_crossover_with_additive_adjust(self):
        cont, rolls = stitch(_two_contracts())
        assert str(rolls.iloc[0]["roll_day"]) == "2026-03-05"
        assert rolls.iloc[0]["offset"] == 10.0

        dc = cont["close"].groupby(cont.index.normalize()).last()
        et = "America/New_York"
        assert dc[pd.Timestamp(DAYS[0], tz=et)] == 110.0  # front, back-adjusted
        assert dc[pd.Timestamp(DAYS[3], tz=et)] == 113.0  # roll day, adjusted
        assert dc[pd.Timestamp(DAYS[4], tz=et)] == 114.0  # next contract, unadjusted

    def test_series_is_continuous_at_roll(self):
        cont, _ = stitch(_two_contracts())
        dc = cont["close"].groupby(cont.index.normalize()).last()
        # no artificial jump: the daily series rises by 1 point per day
        assert dc.diff().dropna().eq(1.0).all()

    def test_no_duplicate_bars(self):
        cont, _ = stitch(_two_contracts())
        assert not cont.index.duplicated().any()


def test_quarterly_expiries_window():
    months = quarterly_expiries(pd.Timestamp("2026-07-11", tz="UTC"))
    assert months[0] == "202409"   # ~2 years back (IB limit)
    assert months[-1] == "202609"  # current front contract
    assert len(months) == 9
