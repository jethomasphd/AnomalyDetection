"""Data fetching module — pulls stock data from Yahoo Finance."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from .config import DEFAULT_TICKERS, MIN_DATA_POINTS, SIGNAL_START_DATE

logger = logging.getLogger(__name__)


def fetch_ticker(
    ticker: str,
    start_date: str = SIGNAL_START_DATE,
    end_date: Optional[datetime] = None,
    lookback_days: Optional[int] = None,  # legacy, ignored when start_date set
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a single ticker from the anchored start date.

    Returns a DataFrame with columns:
        Date, Open, High, Low, Close, Volume, Ticker
    or None if the fetch fails / insufficient data.
    """
    end = end_date or datetime.today()
    start_str = start_date
    # yfinance treats `end` as exclusive, so add a day to include today's bar.
    end_str = (end + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        df = yf.download(
            ticker,
            start=start_str,
            end=end_str,
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", ticker, exc)
        return None

    if df is None or len(df) < MIN_DATA_POINTS:
        logger.warning(
            "Insufficient data for %s (%d rows, need %d)",
            ticker,
            len(df) if df is not None else 0,
            MIN_DATA_POINTS,
        )
        return None

    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # yfinance >=1.4 leaves the datetime index unnamed, so reset_index() yields
    # an "index" column instead of "Date". Name it so the column check below
    # finds "Date" regardless of the installed yfinance version.
    df.index.name = "Date"
    df = df.reset_index()
    df["Ticker"] = ticker

    # Keep only what we need
    cols = ["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]
    for col in cols:
        if col not in df.columns:
            if col == "Volume":
                df[col] = 0
            else:
                return None
    return df[cols].copy()


def fetch_multiple(
    tickers: Optional[list[str]] = None,
    start_date: str = SIGNAL_START_DATE,
    lookback_days: Optional[int] = None,  # legacy, ignored
) -> pd.DataFrame:
    """Fetch data for multiple tickers and combine into one DataFrame."""
    tickers = tickers or DEFAULT_TICKERS
    frames = []

    for ticker in tickers:
        logger.info("Fetching %s ...", ticker)
        df = fetch_ticker(ticker, start_date=start_date)
        if df is not None:
            frames.append(df)

    if not frames:
        raise RuntimeError("No data fetched for any ticker.")

    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"])
    combined = combined.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    logger.info(
        "Fetched %d rows across %d tickers",
        len(combined),
        combined["Ticker"].nunique(),
    )
    return combined


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features used by the detection algorithms.

    Features added per ticker:
        - daily_return: (Close - prev Close) / prev Close
        - log_return: log(Close / prev Close)
        - volatility_20d: 20-day rolling std of daily_return
        - volume_ratio: Volume / 20-day rolling mean Volume
        - price_range: (High - Low) / Close
        - close_zscore: rolling z-score of Close (60-day window)
    """
    import numpy as np

    out = []
    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date").copy()

        g["daily_return"] = g["Close"].pct_change()
        g["log_return"] = np.log(g["Close"] / g["Close"].shift(1))
        g["volatility_20d"] = g["daily_return"].rolling(20).std()

        vol_ma = g["Volume"].rolling(20).mean()
        g["volume_ratio"] = g["Volume"] / vol_ma.replace(0, np.nan)

        g["price_range"] = (g["High"] - g["Low"]) / g["Close"]

        roll_mean = g["Close"].rolling(60).mean()
        roll_std = g["Close"].rolling(60).std()
        g["close_zscore"] = (g["Close"] - roll_mean) / roll_std.replace(0, np.nan)

        out.append(g)

    result = pd.concat(out, ignore_index=True)
    return result
