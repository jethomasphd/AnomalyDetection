"""EWMA (Exponentially Weighted Moving Average) Trend Analysis (causal).

Tracks the deviation of price from its EWMA, standardized by the
deviation's own trailing volatility (per ticker, excluding today). A 3-sigma
stretch means the same thing for a sleepy T-bill fund as it does for NVDA —
each ticker is judged against its own normal behavior.

Trajectory classifies what the stretch is DOING, in sigma units:
  - stable:    deviation magnitude roughly steady
  - extending: |deviation| growing — price pulling further away from trend
  - reverting: |deviation| shrinking — price snapping back toward trend
  - breakout:  extreme standardized deviation (beyond threshold + margin)

Plain-English: "Is this stock's momentum abnormal right now?"
"""

import logging

import numpy as np
import pandas as pd

from ..config import (
    BREAKOUT_SIGMA_MARGIN,
    CAUSAL_WARMUP_BARS,
    EWMA_DEV_VOL_MIN_PERIODS,
    EWMA_DEV_VOL_WINDOW,
    EWMA_SPAN,
    EWMA_TREND_WINDOW,
    SENSITIVITY_PRESETS,
    TRAJECTORY_SLOPE_SIGMA_PER_DAY,
)
from .causal import trailing_std, z_to_unit

logger = logging.getLogger(__name__)


def classify_trajectory(
    dev_z_history: np.ndarray,
    breakout_threshold: float,
    window: int = EWMA_TREND_WINDOW,
) -> str:
    """Classify the trajectory of the standardized deviation at the last bar.

    Operates in sigma units (dev_z = deviation / its trailing volatility):
      - breakout if |dev_z| exceeds breakout_threshold
      - extending/reverting if |dev_z| has been growing/shrinking faster
        than TRAJECTORY_SLOPE_SIGMA_PER_DAY over the last `window` bars
      - stable otherwise
    """
    finite = dev_z_history[np.isfinite(dev_z_history)]
    if len(finite) == 0:
        return "stable"
    if abs(finite[-1]) >= breakout_threshold:
        return "breakout"
    if len(finite) < window:
        return "stable"
    recent = np.abs(finite[-window:])
    slope = np.polyfit(np.arange(window), recent, 1)[0]
    if slope > TRAJECTORY_SLOPE_SIGMA_PER_DAY:
        return "extending"
    if slope < -TRAJECTORY_SLOPE_SIGMA_PER_DAY:
        return "reverting"
    return "stable"


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    span: int = EWMA_SPAN,
) -> pd.DataFrame:
    """Run causal EWMA anomaly detection on each ticker.

    Returns a DataFrame with columns:
        Ticker, Date, ewma_score (0..1, 0.5 = 2 sigma), ewma_anomaly (bool),
        ewma_value, deviation_pct, dev_z, trajectory
    """
    z_threshold = SENSITIVITY_PRESETS[sensitivity]["z_threshold"]
    breakout_threshold = z_threshold + BREAKOUT_SIGMA_MARGIN
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date")
        closes = g["Close"].values.astype(float)
        dates = g["Date"].values
        n = len(closes)

        if n < span:
            logger.info("EWMA: skipping %s (insufficient data)", ticker)
            continue

        ewma = pd.Series(closes).ewm(span=span, adjust=False).mean().values
        deviation_pct = (closes - ewma) / np.where(ewma > 0, ewma, 1e-10) * 100

        sigma = trailing_std(
            deviation_pct, window=EWMA_DEV_VOL_WINDOW, min_periods=EWMA_DEV_VOL_MIN_PERIODS
        )
        dev_z = np.full(n, np.nan)
        valid = (~np.isnan(sigma)) & (sigma > 0)
        dev_z[valid] = deviation_pct[valid] / sigma[valid]

        abs_z = np.abs(np.nan_to_num(dev_z, nan=0.0))
        abs_z[:CAUSAL_WARMUP_BARS] = 0.0
        scores = z_to_unit(abs_z)

        for i in range(n):
            trajectory = classify_trajectory(dev_z[: i + 1], breakout_threshold)
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "ewma_score": round(float(scores[i]), 6),
                    "ewma_anomaly": bool(abs_z[i] > z_threshold),
                    "ewma_value": round(float(ewma[i]), 2),
                    "deviation_pct": round(float(deviation_pct[i]), 2),
                    "dev_z": round(float(dev_z[i]), 3) if np.isfinite(dev_z[i]) else 0.0,
                    "trajectory": trajectory,
                }
            )

    return pd.DataFrame(results)
