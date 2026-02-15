"""EWMA (Exponentially Weighted Moving Average) Trend Analysis for spam rate.

"IT'S BOBSLED TIME"

Tracks the deviation of spam rate from its EWMA trend and classifies
the current trajectory. When this method fires, the momentum is clear —
the trend is locked in and it's time to act.

Trajectory classifications:
  - normal: within expected bands — peace be the journey
  - accelerating: pulling away from trend — building momentum
  - decelerating: reverting toward trend — slowing down
  - breakout: extreme deviation — this is a big move

Plain-English: "Is the spam rate trend picking up speed in the wrong direction?"
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
    """Run EWMA anomaly detection on each domain's spam rate.

    Returns a DataFrame with columns:
        Domain, Date, ewma_score, ewma_anomaly (bool),
        ewma_value, deviation_pct, trajectory
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        spam_rate = g["SpamRate"].values.astype(float)
        dates = g["Date"].values

        if len(spam_rate) < span:
            logger.info("EWMA: skipping %s (insufficient data)", domain)
            continue

        ewma_vals = pd.Series(spam_rate).ewm(span=span, adjust=False).mean().values

        # Deviation as % of EWMA
        deviation = (spam_rate - ewma_vals) / np.where(ewma_vals > 0, ewma_vals, 1e-10)

        # Normalize absolute deviation to [0, 1]
        abs_dev = np.abs(deviation)
        dev_max = abs_dev.max()
        if dev_max > 0:
            scores = abs_dev / dev_max
        else:
            scores = abs_dev

        threshold = np.percentile(scores[scores > 0], preset["percentile"]) if np.any(scores > 0) else 0

        for i in range(len(spam_rate)):
            trajectory = _classify_trajectory(deviation[: i + 1])
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "ewma_score": round(float(scores[i]), 6),
                    "ewma_anomaly": bool(scores[i] > threshold) if threshold > 0 else False,
                    "ewma_value": round(float(ewma_vals[i]), 6),
                    "deviation_pct": round(float(deviation[i] * 100), 2),
                    "trajectory": trajectory,
                }
            )

    return pd.DataFrame(results)
