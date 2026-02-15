"""Data loading module — reads Google Postmaster spam rate data.

Simplified ETL: one file in, clean data out. No merging, no fuss.
Just Postmaster.csv -> filtered, feature-engineered DataFrame.

"Before you can cross the finish line, you have to start the race."
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_DATA_PATH, MIN_DATA_POINTS, VALID_REPUTATIONS

logger = logging.getLogger(__name__)


def load_data(
    data_path: str = DEFAULT_DATA_PATH,
    domains: Optional[list[str]] = None,
    min_data_points: int = MIN_DATA_POINTS,
) -> pd.DataFrame:
    r"""Load Google Postmaster data and filter to qualifying domains.

    This is the entire ETL pipeline — one CSV in, clean data out:
      1. Read Postmaster.csv (\\N values become NaN)
      2. Keep only domains with MEDIUM or HIGH reputation
      3. Drop rows where SpamRate is missing
      4. Keep only domains with enough history (>= min_data_points days)

    Returns a DataFrame with columns:
        Domain, Date, SpamRate, DomainReputation,
        DkimSuccess, DmarcSuccess, SpfSuccess, InboundEncryption
    """
    logger.info("Loading Postmaster data from %s", data_path)
    df = pd.read_csv(data_path, na_values="\\N")

    # Standardize column names for clarity
    df = df.rename(columns={
        "domain": "Domain",
        "date": "Date",
        "userReportedSpamRatio": "SpamRate",
        "domainReputation": "DomainReputation",
        "dkimSuccessRatio": "DkimSuccess",
        "dmarcSuccessRatio": "DmarcSuccess",
        "spfSuccessRatio": "SpfSuccess",
        "inboundEncryptionRatio": "InboundEncryption",
    })

    df["Date"] = pd.to_datetime(df["Date"])

    logger.info("Raw data: %d rows, %d domains", len(df), df["Domain"].nunique())

    # --- Filter 1: Only domains with MEDIUM or HIGH reputation on their MOST RECENT date ---
    # We check each domain's reputation on its latest date of record.
    # If a domain's most recent reputation is LOW or NONE, we exclude it entirely.
    # This ensures we only monitor domains that currently have standing with Google.
    rows_before = len(df)
    latest_date_per_domain = df.sort_values("Date").groupby("Domain").tail(1)
    qualifying_domains = latest_date_per_domain[
        latest_date_per_domain["DomainReputation"].isin(VALID_REPUTATIONS)
    ]["Domain"].unique()
    df = df[df["Domain"].isin(qualifying_domains)]
    logger.info(
        "Reputation filter (MEDIUM/HIGH on most recent date): kept %d of %d rows (%d domains)",
        len(df), rows_before, df["Domain"].nunique(),
    )

    # --- Filter 2: Drop rows where SpamRate is missing ---
    rows_before = len(df)
    df = df.dropna(subset=["SpamRate"])
    rows_dropped = rows_before - len(df)
    if rows_dropped > 0:
        logger.info("Dropped %d rows with missing SpamRate (%d remaining)", rows_dropped, len(df))

    # --- Filter 3: Specific domains if requested ---
    if domains:
        df = df[df["Domain"].isin(domains)]
        if df.empty:
            raise RuntimeError(f"No data found for specified domains: {domains}")

    # --- Filter 4: Enough history ---
    domain_counts = df.groupby("Domain").size()
    qualifying = domain_counts[domain_counts >= min_data_points].index
    domains_before = df["Domain"].nunique()
    df = df[df["Domain"].isin(qualifying)]
    domains_dropped = domains_before - df["Domain"].nunique()
    if domains_dropped > 0:
        logger.info(
            "Dropped %d domains with < %d days of data — %d domains remaining",
            domains_dropped, min_data_points, df["Domain"].nunique(),
        )

    if df.empty:
        raise RuntimeError(
            f"No domains qualify (need >= {min_data_points} days of data "
            f"with MEDIUM or HIGH reputation)"
        )

    # Keep relevant columns
    keep_cols = [
        "Domain", "Date", "SpamRate", "DomainReputation",
        "DkimSuccess", "DmarcSuccess", "SpfSuccess", "InboundEncryption",
    ]
    for col in keep_cols:
        if col not in df.columns:
            df[col] = np.nan

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
        - spam_rate_change: day-over-day percentage change in SpamRate
        - volatility_7d: 7-day rolling standard deviation of SpamRate
        - spam_rate_zscore: 30-day rolling z-score of SpamRate
        - spam_rate_ma7: 7-day moving average (smoothed trend)
    """
    out = []
    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()

        # Day-over-day change
        g["spam_rate_change"] = g["SpamRate"].pct_change()

        # 7-day rolling volatility
        g["volatility_7d"] = g["SpamRate"].rolling(7).std()

        # 30-day rolling z-score
        roll_mean = g["SpamRate"].rolling(30).mean()
        roll_std = g["SpamRate"].rolling(30).std()
        g["spam_rate_zscore"] = (g["SpamRate"] - roll_mean) / roll_std.replace(0, np.nan)

        # 7-day smoothed moving average
        g["spam_rate_ma7"] = g["SpamRate"].rolling(7).mean()

        out.append(g)

    result = pd.concat(out, ignore_index=True)
    return result
