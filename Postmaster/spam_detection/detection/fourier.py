"""Fourier Transform anomaly detection for Google Postmaster spam rate data.

"FEEL THE RHYTHM"

Every sending domain has a characteristic spam rate "rhythm" — how the
ratio of user-reported spam oscillates over time due to send cadence,
list quality changes, and seasonal effects. The Fourier Transform
decomposes the spam rate series into frequency components. When the
energy distribution shifts significantly from historical norms, it
signals a structural change in how recipients perceive your email.

Plain-English: "Has the *rhythm* of this domain's spam rate changed?"
"""

import logging

import numpy as np
import pandas as pd
from scipy.fft import fft

from ..config import FOURIER_TOP_K, FOURIER_WINDOW, SENSITIVITY_PRESETS

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
    window: int = FOURIER_WINDOW,
) -> pd.DataFrame:
    """Run Fourier anomaly detection on each domain's spam rate.

    Returns a DataFrame with columns:
        Domain, Date, fourier_score, fourier_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        spam_rate = g["SpamRate"].values.astype(np.float64)
        dates = g["Date"].values

        if len(spam_rate) < window + FOURIER_TOP_K:
            logger.info("Fourier: skipping %s (insufficient data)", domain)
            continue

        # Full-history baseline spectrum
        baseline = _spectral_energy(spam_rate)

        scores = np.zeros(len(spam_rate))
        for i in range(window, len(spam_rate)):
            segment = spam_rate[i - window : i]
            current = _spectral_energy(segment)
            # Symmetric KL-like divergence (epsilon-smoothed)
            eps = 1e-10
            b = baseline + eps
            c = current + eps
            divergence = 0.5 * np.sum(c * np.log(c / b) + b * np.log(b / c))
            scores[i] = divergence

        threshold = np.percentile(scores[scores > 0], preset["percentile"]) if np.any(scores > 0) else 0

        for i in range(len(spam_rate)):
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "fourier_score": round(float(scores[i]), 6),
                    "fourier_anomaly": bool(scores[i] > threshold) if threshold > 0 else False,
                }
            )

    return pd.DataFrame(results)
