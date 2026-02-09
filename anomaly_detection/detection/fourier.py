"""Fourier Transform anomaly detection.

Detects structural changes in the frequency-domain energy distribution
of a price series. When the spectrum shifts significantly from historical
norms, it signals a regime change (e.g., shift from mean-reversion to
trending behavior).

Plain-English: "Has the *rhythm* of this stock changed?"
"""

import logging

import numpy as np
import pandas as pd
from scipy.fft import fft, fftfreq

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
    # Sort by power descending, take top k
    top_idx = np.argsort(power)[::-1][:top_k]
    return power[top_idx] / total


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    window: int = 60,
) -> pd.DataFrame:
    """Run Fourier anomaly detection on each ticker.

    Compares the spectral energy distribution of a trailing window
    against the full historical baseline using KL-divergence-inspired
    distance.

    Returns a DataFrame with columns:
        Ticker, Date, fourier_score, fourier_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date").copy()
        closes = g["Close"].values
        dates = g["Date"].values

        if len(closes) < window + FOURIER_TOP_K:
            logger.info("Fourier: skipping %s (insufficient data)", ticker)
            continue

        # Full-history baseline spectrum
        baseline = _spectral_energy(closes)

        scores = np.zeros(len(closes))
        for i in range(window, len(closes)):
            segment = closes[i - window : i]
            current = _spectral_energy(segment)
            # Symmetric KL-like divergence (epsilon-smoothed)
            eps = 1e-10
            b = baseline + eps
            c = current + eps
            divergence = 0.5 * np.sum(c * np.log(c / b) + b * np.log(b / c))
            scores[i] = divergence

        threshold = np.percentile(scores[scores > 0], preset["percentile"]) if np.any(scores > 0) else 0

        for i in range(len(closes)):
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "fourier_score": round(float(scores[i]), 6),
                    "fourier_anomaly": bool(scores[i] > threshold) if threshold > 0 else False,
                }
            )

    return pd.DataFrame(results)
