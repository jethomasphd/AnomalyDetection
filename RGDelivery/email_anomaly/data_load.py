"""Data loading module — reads email click data from CSV."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_DATA_PATH, MIN_DATA_POINTS, MIN_DAILY_CLICKS, MIN_DAILY_SENDS

logger = logging.getLogger(__name__)


def load_data(
    data_path: str = DEFAULT_DATA_PATH,
    domains: Optional[list[str]] = None,
    min_data_points: int = MIN_DATA_POINTS,
    min_daily_sends: int = MIN_DAILY_SENDS,
    min_daily_clicks: int = MIN_DAILY_CLICKS,
) -> pd.DataFrame:
    """Load email click data from CSV and filter to qualifying domains.

    Returns a DataFrame with columns:
        Domain, Date, Clicks, Sent, Delivered, Opens, Unsubscribes,
        Complaints, Blocks, HardBounces, SoftBounces
    """
    logger.info("Loading data from %s", data_path)
    df = pd.read_csv(data_path)

    # Standardize column names
    df = df.rename(columns={
        "Sending Domain": "Domain",
        "Hard Bounces": "HardBounces",
        "Soft Bounces": "SoftBounces",
    })

    df["Date"] = pd.to_datetime(df["Date"])

    # Drop rows where Sent < 5000 (low-volume sends are noise)
    rows_before = len(df)
    df = df[df["Sent"] >= 5000]
    rows_dropped = rows_before - len(df)
    if rows_dropped > 0:
        logger.info("Dropped %d rows with Sent < 5000 (%d remaining)", rows_dropped, len(df))

    # Filter to specific domains if provided
    if domains:
        df = df[df["Domain"].isin(domains)]
        if df.empty:
            raise RuntimeError(f"No data found for specified domains: {domains}")

    # Filter to domains with enough data points
    domain_counts = df.groupby("Domain").size()
    qualifying = domain_counts[domain_counts >= min_data_points].index
    df = df[df["Domain"].isin(qualifying)]

    # Filter to domains with sufficient send volume and click volume
    domain_stats = df.groupby("Domain").agg(avg_sent=("Sent", "mean"), avg_clicks=("Clicks", "mean"))
    qualifying = domain_stats[
        (domain_stats["avg_sent"] >= min_daily_sends)
        & (domain_stats["avg_clicks"] >= min_daily_clicks)
    ].index
    domains_before = df["Domain"].nunique()
    df = df[df["Domain"].isin(qualifying)]
    domains_dropped = domains_before - df["Domain"].nunique()
    if domains_dropped > 0:
        logger.info(
            "Dropped %d domains below volume thresholds (avg sends >= %d, avg clicks >= %d) — %d domains remaining",
            domains_dropped, min_daily_sends, min_daily_clicks, df["Domain"].nunique(),
        )

    if df.empty:
        raise RuntimeError(
            f"No domains qualify (need >= {min_data_points} days, "
            f">= {min_daily_sends} avg daily sends, "
            f"and >= {min_daily_clicks} avg daily clicks)"
        )

    # Keep relevant columns
    keep_cols = [
        "Domain", "Date", "Clicks", "Sent", "Delivered", "Opens",
        "Unsubscribes", "Complaints", "Blocks", "HardBounces", "SoftBounces",
    ]
    for col in keep_cols:
        if col not in df.columns:
            df[col] = 0

    df = df[keep_cols].copy()
    df = df.sort_values(["Domain", "Date"]).reset_index(drop=True)

    logger.info(
        "Loaded %d rows across %d qualifying domains (date range: %s to %s)",
        len(df),
        df["Domain"].nunique(),
        df["Date"].min().strftime("%Y-%m-%d"),
        df["Date"].max().strftime("%Y-%m-%d"),
    )
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features used by the detection algorithms.

    Features added per domain:
        - click_change: day-over-day change in clicks
        - click_rate: Clicks / Delivered (when Delivered > 0)
        - volatility_20d: 20-day rolling std of click_change
        - delivery_rate: Delivered / Sent (when Sent > 0)
        - click_zscore: rolling z-score of Clicks (30-day window)
    """
    out = []
    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()

        g["click_change"] = g["Clicks"].pct_change()

        delivered = g["Delivered"].replace(0, np.nan)
        g["click_rate"] = g["Clicks"] / delivered

        g["volatility_20d"] = g["click_change"].rolling(20).std()

        sent = g["Sent"].replace(0, np.nan)
        g["delivery_rate"] = g["Delivered"] / sent

        roll_mean = g["Clicks"].rolling(30).mean()
        roll_std = g["Clicks"].rolling(30).std()
        g["click_zscore"] = (g["Clicks"] - roll_mean) / roll_std.replace(0, np.nan)

        out.append(g)

    result = pd.concat(out, ignore_index=True)
    return result
