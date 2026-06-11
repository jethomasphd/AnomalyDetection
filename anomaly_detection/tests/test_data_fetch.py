"""Final-bars-only guard: intraday snapshots must never become frozen verdicts."""

from datetime import datetime

import numpy as np
import pandas as pd

from anomaly_detection.data_fetch import drop_partial_intraday_bar


def _frame(last_date: str, n: int = 5) -> pd.DataFrame:
    dates = pd.bdate_range(end=last_date, periods=n)
    return pd.DataFrame({"Close": np.arange(n, dtype=float) + 100}, index=dates)


def test_partial_today_bar_dropped_before_close():
    df = _frame("2026-06-11")
    now = datetime(2026, 6, 11, 14, 30)  # 14:30 UTC — US market open
    out = drop_partial_intraday_bar(df, now_utc=now)
    assert len(out) == len(df) - 1
    assert out.index[-1].strftime("%Y-%m-%d") == "2026-06-10"


def test_today_bar_kept_after_close():
    df = _frame("2026-06-11")
    now = datetime(2026, 6, 11, 22, 5)  # after the scheduled post-close run time
    out = drop_partial_intraday_bar(df, now_utc=now)
    assert len(out) == len(df)


def test_historical_frames_untouched():
    df = _frame("2026-06-10")
    now = datetime(2026, 6, 11, 14, 30)  # midday, but last bar is yesterday's final
    out = drop_partial_intraday_bar(df, now_utc=now)
    assert len(out) == len(df)


def test_empty_and_none_passthrough():
    assert drop_partial_intraday_bar(None) is None
    empty = pd.DataFrame()
    assert len(drop_partial_intraday_bar(empty)) == 0
