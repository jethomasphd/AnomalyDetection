"""Shared synthetic-data fixtures for the detection test suite."""

import numpy as np
import pandas as pd
import pytest

from anomaly_detection.data_fetch import compute_features


def make_price_frame(closes: np.ndarray, ticker: str, seed: int = 0) -> pd.DataFrame:
    """OHLCV frame on a business-day calendar from a close series."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-11-01", periods=len(closes))
    return pd.DataFrame({
        "Date": dates,
        "Open": closes,
        "High": closes * 1.005,
        "Low": closes * 0.995,
        "Close": closes,
        "Volume": rng.integers(1_000_000, 5_000_000, len(closes)).astype(float),
        "Ticker": ticker,
    })


@pytest.fixture(scope="session")
def synthetic_features() -> pd.DataFrame:
    """Three deterministic tickers, 240 bars each, features computed once.

    WALK  — plain geometric random walk (no injected anomaly)
    QUIET — near-constant, BIL-like series (~0.01% daily moves)
    CRASH — same walk with a violent 5-day, ~22% crash at bar 180
    """
    rng = np.random.default_rng(7)
    n = 240
    walk = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    quiet = 91.5 + np.cumsum(rng.normal(0.002, 0.012, n)) / 100
    crash = walk.copy()
    crash[180:185] = crash[180:185] * np.exp(np.cumsum(np.full(5, -0.05)))
    crash[185:] = crash[185:] * np.exp(-0.25)

    df = pd.concat(
        [
            make_price_frame(walk, "WALK", seed=1),
            make_price_frame(quiet, "QUIET", seed=2),
            make_price_frame(crash, "CRASH", seed=3),
        ],
        ignore_index=True,
    )
    return compute_features(df)
