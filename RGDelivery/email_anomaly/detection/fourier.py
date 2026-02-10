"""Fourier Transform anomaly detection for email click data.

Detects structural changes in the frequency-domain energy distribution
of a click time series. When the spectrum shifts significantly from
historical norms, it signals a regime change in engagement patterns.

Plain-English: "Has the *rhythm* of this domain's clicks changed?"
"""

import logging

import numpy as np
import pandas as pd
from scipy.fft import fft

from ..config import FOURIER_TOP_K, SENSITIVITY_PRESETS

logger = logging.getLogger(__name__)


def _spectral_energy(series: np.ndarray, top_k: int = FOURIER_TOP_K) -> np.ndarray:
    """Return the normalized energy of the top-k frequency components."""
    n = len(series)
    yf = fft(series - np.mean(series))  # Remove DC component
    power = np.abs(yf[: n // 2]) ** 2
    total = power.sum()
    if total == 0:
        return np.zeros(top_k)
    top_idx = np.argsort(power)[::-1][:top_k]
    return power[top_idx] / total


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    window: int = 30,
) -> pd.DataFrame:
    """Run Fourier anomaly detection on each domain.

    Uses a shorter window (30 days) than the stock system (60 days)
    since email datasets typically have shorter history.

    Returns a DataFrame with columns:
        Domain, Date, fourier_score, fourier_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        clicks = g["Clicks"].values.astype(np.float64)
        dates = g["Date"].values

        if len(clicks) < window + FOURIER_TOP_K:
            logger.info("Fourier: skipping %s (insufficient data)", domain)
            continue

        # Full-history baseline spectrum
        baseline = _spectral_energy(clicks)

        scores = np.zeros(len(clicks))
        for i in range(window, len(clicks)):
            segment = clicks[i - window : i]
            current = _spectral_energy(segment)
            # Symmetric KL-like divergence (epsilon-smoothed)
            eps = 1e-10
            b = baseline + eps
            c = current + eps
            divergence = 0.5 * np.sum(c * np.log(c / b) + b * np.log(b / c))
            scores[i] = divergence

        threshold = np.percentile(scores[scores > 0], preset["percentile"]) if np.any(scores > 0) else 0

        for i in range(len(clicks)):
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "fourier_score": round(float(scores[i]), 6),
                    "fourier_anomaly": bool(scores[i] > threshold) if threshold > 0 else False,
                }
            )

    return pd.DataFrame(results)
