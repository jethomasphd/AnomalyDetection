"""EWMA (Exponentially Weighted Moving Average) Trend Analysis.

Tracks the deviation of price from its EWMA and classifies the
current trajectory as one of:
  - normal: within expected bands
  - accelerating: pulling away from the trend (bullish or bearish)
  - decelerating: reverting toward the trend
  - breakout: extreme deviation from EWMA (potential opportunity/risk)

Plain-English: "Is this stock's momentum abnormal right now?"
"""

import logging

import numpy as np
import pandas as pd

from ..config import EWMA_SPAN, EWMA_TREND_WINDOW, SENSITIVITY_PRESETS

logger = logging.getLogger(__name__)


def _classify_trajectory(deviations: np.ndarray, window: int = EWMA_TREND_WINDOW) -> str:
    """Classify the recent trend trajectory."""
    if len(deviations) < window:
        return "normal"
    recent = deviations[-window:]
    slope = np.polyfit(range(window), recent, 1)[0]
    magnitude = abs(recent[-1])

    if magnitude > 0.8:
        return "breakout"
    elif slope > 0.02:
        return "accelerating"
    elif slope < -0.02:
        return "decelerating"
    return "normal"


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    span: int = EWMA_SPAN,
) -> pd.DataFrame:
    """Run EWMA anomaly detection on each ticker.

    Returns a DataFrame with columns:
        Ticker, Date, ewma_score, ewma_anomaly (bool),
        ewma_value, deviation, trajectory
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date").copy()
        closes = g["Close"].values.astype(float)
        dates = g["Date"].values

        if len(closes) < span:
            logger.info("EWMA: skipping %s (insufficient data)", ticker)
            continue

        ewma = pd.Series(closes).ewm(span=span, adjust=False).mean().values

        # Deviation as % of EWMA
        deviation = (closes - ewma) / np.where(ewma > 0, ewma, 1e-10)

        # Normalize absolute deviation to [0, 1]
        abs_dev = np.abs(deviation)
        dev_max = abs_dev.max()
        if dev_max > 0:
            scores = abs_dev / dev_max
        else:
            scores = abs_dev

        threshold = np.percentile(scores[scores > 0], preset["percentile"]) if np.any(scores > 0) else 0

        for i in range(len(closes)):
            trajectory = _classify_trajectory(deviation[: i + 1])
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "ewma_score": round(float(scores[i]), 6),
                    "ewma_anomaly": bool(scores[i] > threshold) if threshold > 0 else False,
                    "ewma_value": round(float(ewma[i]), 2),
                    "deviation_pct": round(float(deviation[i] * 100), 2),
                    "trajectory": trajectory,
                }
            )

    return pd.DataFrame(results)
