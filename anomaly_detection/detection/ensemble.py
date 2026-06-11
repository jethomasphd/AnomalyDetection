"""Custom Ensemble anomaly detection (causal).

Combines three complementary approaches:
  1. Z-Score (40%) — today's return standardized by the ticker's own
     trailing return volatility (excluding today). Stationary by
     construction, unlike z-scoring raw price levels.
  2. Seasonal Decomposition (30%) — one-sided additive decomposition:
     trailing trend (one-sided moving average) + weekday seasonal means
     learned from PAST bars only; the residual is standardized by its own
     trailing volatility. This is the causal counterpart of
     statsmodels.seasonal_decompose(two_sided=False), which the test suite
     uses as the reference implementation.
  3. Isolation Forest (30%) — walk-forward: the forest is refit on a
     trailing window at fixed calendar blocks and only ever scores bars
     that come strictly AFTER its training data. No bar is scored by a
     model that saw it (or its future) during training.

Each component yields a non-negative z-like score; the weighted blend is
the ensemble z. Nothing at bar t uses data after bar t.

Plain-English: "Do multiple independent tests agree something is unusual?"
"""

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ..config import (
    CAUSAL_WARMUP_BARS,
    ENSEMBLE_WEIGHTS,
    IFOREST_REFIT_EVERY,
    IFOREST_TRAIN_WINDOW,
    SEASONAL_PERIOD,
    SEASONAL_TREND_WINDOW,
    SENSITIVITY_PRESETS,
)
from .causal import causal_robust_z, trailing_std, z_to_unit

logger = logging.getLogger(__name__)


def _return_zscores(returns: np.ndarray, window: int = 60, min_periods: int = 20) -> np.ndarray:
    """|today's return| / trailing std of returns (excluding today)."""
    sig = trailing_std(returns, window=window, min_periods=min_periods)
    z = np.zeros(len(returns))
    valid = (~np.isnan(returns)) & (~np.isnan(sig)) & (sig > 0)
    z[valid] = np.abs(returns[valid]) / sig[valid]
    return z


def _seasonal_residual_zscores(
    closes: np.ndarray,
    weekdays: np.ndarray,
    period: int = SEASONAL_PERIOD,
    trend_window: int = SEASONAL_TREND_WINDOW,
) -> np.ndarray:
    """Causal additive decomposition residual, standardized.

    residual[t] = close[t] - trend[t] - seasonal[weekday(t)]
      trend[t]    = mean of closes[t-trend_window+1 .. t]   (one-sided)
      seasonal[w] = mean of detrended values on weekday w over bars < t
                    (expanding, strictly past)

    The residual is then divided by its own trailing std (excluding today).
    """
    n = len(closes)
    s = pd.Series(closes)
    trend = s.rolling(trend_window, min_periods=trend_window).mean().values
    detrended = closes - trend  # NaN during trend warmup

    seasonal = np.zeros(n)
    sums = np.zeros(period)
    counts = np.zeros(period)
    for t in range(n):
        w = int(weekdays[t]) % period
        if counts[w] > 0:
            seasonal[t] = sums[w] / counts[w]
        # Update AFTER reading: bar t's own detrended value only informs
        # the seasonal estimate of later bars.
        if not np.isnan(detrended[t]):
            sums[w] += detrended[t]
            counts[w] += 1

    residual = detrended - seasonal
    sig = trailing_std(residual, window=60, min_periods=20)
    z = np.zeros(n)
    valid = (~np.isnan(residual)) & (~np.isnan(sig)) & (sig > 0)
    z[valid] = np.abs(residual[valid]) / sig[valid]
    return z


def _iforest_walkforward_scores(features: np.ndarray) -> np.ndarray:
    """Walk-forward Isolation Forest raw outlier scores.

    Refit every IFOREST_REFIT_EVERY bars on the trailing
    IFOREST_TRAIN_WINDOW bars that end strictly BEFORE the block being
    scored. Block boundaries are fixed at absolute bar indices, so scores
    are prefix-invariant: appending future bars never changes an earlier
    block's model or scores.
    """
    n = len(features)
    raw = np.zeros(n)
    feat = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    first_block = ((CAUSAL_WARMUP_BARS // IFOREST_REFIT_EVERY) + 1) * IFOREST_REFIT_EVERY
    for block_start in range(first_block, n, IFOREST_REFIT_EVERY):
        train_lo = max(0, block_start - IFOREST_TRAIN_WINDOW)
        X_train = feat[train_lo:block_start]
        if len(X_train) < 30:
            continue
        clf = IsolationForest(contamination="auto", random_state=42, n_estimators=100)
        clf.fit(X_train)
        block_end = min(block_start + IFOREST_REFIT_EVERY, n)
        # score_samples returns negative values for outliers; flip sign so
        # bigger = weirder, and shift by the offset so values are >= 0-ish.
        raw[block_start:block_end] = -clf.score_samples(feat[block_start:block_end])
    return raw


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
) -> pd.DataFrame:
    """Run causal ensemble anomaly detection on each ticker.

    Returns a DataFrame with columns:
        Ticker, Date, ensemble_score (0..1), ensemble_z, ensemble_anomaly,
        zscore_component, seasonal_component, iforest_component
        (components are reported on the same 0..1 scale).
    """
    z_threshold = SENSITIVITY_PRESETS[sensitivity]["z_threshold"]
    w = ENSEMBLE_WEIGHTS
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date")
        closes = g["Close"].values.astype(float)
        dates = g["Date"].values
        n = len(closes)

        if n < CAUSAL_WARMUP_BARS + 10:
            logger.info("Ensemble: skipping %s (insufficient data)", ticker)
            continue

        returns = (
            g["daily_return"].values.astype(float)
            if "daily_return" in g.columns
            else np.concatenate([[np.nan], np.diff(closes) / np.maximum(closes[:-1], 1e-10)])
        )
        vol = (
            g["volatility_20d"].values.astype(float)
            if "volatility_20d" in g.columns
            else np.full(n, np.nan)
        )
        volume_ratio = (
            g["volume_ratio"].values.astype(float)
            if "volume_ratio" in g.columns
            else np.zeros(n)
        )
        price_range = (
            g["price_range"].values.astype(float)
            if "price_range" in g.columns
            else np.zeros(n)
        )
        weekdays = pd.to_datetime(g["Date"]).dt.dayofweek.values

        z_z = _return_zscores(returns)
        s_z = _seasonal_residual_zscores(closes, weekdays)

        # Stationary feature matrix — deliberately NO raw price level, so an
        # all-time high is not "anomalous" by construction.
        features = np.column_stack([returns, vol, volume_ratio, price_range])
        i_raw = _iforest_walkforward_scores(features)
        i_z = causal_robust_z(i_raw, valid_from=CAUSAL_WARMUP_BARS)

        combined_z = w["zscore"] * z_z + w["seasonal"] * s_z + w["isolation_forest"] * i_z
        combined_z[:CAUSAL_WARMUP_BARS] = 0.0
        scores = z_to_unit(combined_z)

        z_unit, s_unit, i_unit = z_to_unit(z_z), z_to_unit(s_z), z_to_unit(i_z)
        for i in range(n):
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "ensemble_score": round(float(scores[i]), 6),
                    "ensemble_z": round(float(combined_z[i]), 4),
                    "ensemble_anomaly": bool(combined_z[i] > z_threshold),
                    "zscore_component": round(float(z_unit[i]), 4),
                    "seasonal_component": round(float(s_unit[i]), 4),
                    "iforest_component": round(float(i_unit[i]), 4),
                }
            )

    return pd.DataFrame(results)
