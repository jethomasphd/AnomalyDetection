"""Ticker validation — checks yfinance compatibility before including tickers."""

import logging
from datetime import datetime, timedelta

import yfinance as yf

from .config import TICKER_REGISTRY

logger = logging.getLogger(__name__)


def validate_ticker(ticker: str, min_rows: int = 5) -> dict:
    """Validate a single ticker against yfinance.

    Returns a dict with:
        ticker, valid (bool), rows_fetched, error (str or None),
        market_cap (float or None)
    """
    result = {"ticker": ticker, "valid": False, "rows_fetched": 0,
              "error": None, "market_cap": None}
    try:
        end = datetime.today()
        start = end - timedelta(days=30)
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False,
                         auto_adjust=True)
        if df is None or len(df) < min_rows:
            result["error"] = f"Insufficient data: {len(df) if df is not None else 0} rows"
            result["rows_fetched"] = len(df) if df is not None else 0
            return result

        result["rows_fetched"] = len(df)
        result["valid"] = True

        # Try to get market cap
        try:
            info = yf.Ticker(ticker).info
            result["market_cap"] = info.get("marketCap")
        except Exception:
            pass  # market cap is optional

    except Exception as exc:
        result["error"] = str(exc)

    return result


def validate_all_tickers(tickers: list[str] | None = None) -> dict:
    """Validate all tickers (or a subset) and return results.

    Returns:
        {
            "valid": [list of valid tickers],
            "invalid": [list of {ticker, error}],
            "market_caps": {ticker: cap_or_none},
            "details": [full validation dicts]
        }
    """
    tickers = tickers or list(TICKER_REGISTRY.keys())
    valid = []
    invalid = []
    market_caps = {}
    details = []

    for ticker in tickers:
        logger.info("Validating %s ...", ticker)
        result = validate_ticker(ticker)
        details.append(result)

        if result["valid"]:
            valid.append(ticker)
            market_caps[ticker] = result["market_cap"]
        else:
            invalid.append({"ticker": ticker, "error": result["error"]})
            logger.warning("Ticker %s FAILED validation: %s", ticker, result["error"])

    logger.info("Validation complete: %d valid, %d invalid out of %d",
                len(valid), len(invalid), len(tickers))
    return {
        "valid": valid,
        "invalid": invalid,
        "market_caps": market_caps,
        "details": details,
    }
