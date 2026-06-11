"""Fourier Transform anomaly detection (causal).

Detects structural change in how a price series distributes its energy
across frequencies. For each bar t we compare the spectral-energy
concentration of the trailing window ending at t against a baseline
spectrum computed from ALL bars up to t (expanding, never the future),
using a symmetric KL-style divergence.

The raw divergence stream is standardized against its own expanding
history (robust z), so the flag means: "today's rhythm-shift is large
relative to every rhythm-shift this ticker has shown so far."

Plain-English: "Has the *rhythm* of this stock changed?"
"""

import logging

import numpy as np
import pandas as pd
from scipy.fft import fft

from ..config import (
    CAUSAL_WARMUP_BARS,
    FOURIER_TOP_K,
    FOURIER_WINDOW,
    SENSITIVITY_PRESETS,
)
from .causal import causal_robust_z, z_to_unit

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
    out = power[top_idx] / total
    if len(out) < top_k:
        out = np.pad(out, (0, top_k - len(out)))
    return out


def _divergence(current: np.ndarray, baseline: np.ndarray) -> float:
    """Symmetric KL-like divergence between two top-k energy profiles."""
    eps = 1e-10
    b = baseline + eps
    c = current + eps
    return float(0.5 * np.sum(c * np.log(c / b) + b * np.log(b / c)))


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    window: int = FOURIER_WINDOW,
) -> pd.DataFrame:
    """Run causal Fourier anomaly detection on each ticker.

    For bar t (t >= window): divergence between the spectrum of
    closes[t-window+1 .. t] and the spectrum of closes[0 .. t].
    Both operands end at t — nothing after t is ever touched.

    Returns a DataFrame with columns:
        Ticker, Date, fourier_score (0..1, 0.5 = 2 sigma),
        fourier_z, fourier_anomaly (bool)
    """
    z_threshold = SENSITIVITY_PRESETS[sensitivity]["z_threshold"]
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date")
        closes = g["Close"].values.astype(float)
        dates = g["Date"].values
        n = len(closes)

        if n < window + FOURIER_TOP_K:
            logger.info("Fourier: skipping %s (insufficient data)", ticker)
            continue

        raw = np.zeros(n)
        for t in range(window, n):
            current = _spectral_energy(closes[t - window + 1 : t + 1])
            baseline = _spectral_energy(closes[: t + 1])
            raw[t] = _divergence(current, baseline)

        warmup = max(window, CAUSAL_WARMUP_BARS)
        z = causal_robust_z(raw, valid_from=warmup)
        scores = z_to_unit(z)

        for i in range(n):
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "fourier_score": round(float(scores[i]), 6),
                    "fourier_z": round(float(z[i]), 4),
                    "fourier_anomaly": bool(z[i] > z_threshold),
                }
            )

    return pd.DataFrame(results)
