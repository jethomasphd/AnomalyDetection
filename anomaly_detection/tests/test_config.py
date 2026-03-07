"""Tests for ticker registry and config."""

from anomaly_detection.config import (
    TICKER_REGISTRY,
    DEFAULT_TICKERS,
    TICKER_NAMES,
    TICKER_SECTORS,
    CATEGORY_LABELS,
    get_default_tickers,
    tickers_by_category,
    ticker_display,
)


def test_registry_has_required_tickers():
    """All specified default tickers must be in the registry."""
    required = [
        # Core Infrastructure
        "CAT", "DE", "HON", "LMT", "GE", "WMT", "COST", "HD", "JNJ", "PFE",
        "ADM", "BG", "TSN", "SCHW", "BRK-B",
        # Critical Choke Points
        "NEE", "D", "KMI", "WMB", "V", "MA", "JPM", "MSFT", "AMZN", "GOOGL",
        "UNP", "NSC", "MCK", "UNH",
        # Big Tech
        "AAPL", "NVDA", "META", "TSLA", "NFLX", "CRM", "AMD", "ORCL",
        # Consumer Leaders
        "PG", "KO", "PEP", "MCD", "NKE", "SBUX", "TGT", "LOW",
        # Financial Titans
        "GS", "MS", "BAC", "C", "WFC", "BLK",
        # Healthcare & Pharma
        "LLY", "ABBV", "MRK", "AMGN", "BMY",
        # Energy & Commodities
        "XOM", "CVX", "COP",
        # Wall Street's Darlings
        "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "VGT", "XLF", "XLE",
        # Reserve
        "BIL",
        # UBS Funds
        "DVRUX", "QGRPX", "BNUEX",
    ]
    for t in required:
        assert t in TICKER_REGISTRY, f"{t} missing from registry"


def test_registry_fields():
    """Every registry entry must have name, category, is_fund, sector."""
    for ticker, info in TICKER_REGISTRY.items():
        assert "name" in info, f"{ticker} missing 'name'"
        assert "category" in info, f"{ticker} missing 'category'"
        assert "is_fund" in info, f"{ticker} missing 'is_fund'"
        assert "sector" in info, f"{ticker} missing 'sector'"
        assert info["category"] in CATEGORY_LABELS, f"{ticker} has unknown category {info['category']}"


def test_ubs_funds_marked_as_fund():
    for t in ("DVRUX", "QGRPX", "BNUEX"):
        assert TICKER_REGISTRY[t]["is_fund"] is True


def test_brk_b_format():
    """BRK-B must use Yahoo Finance format with dash, not dot."""
    assert "BRK-B" in TICKER_REGISTRY
    assert "BRK.B" not in TICKER_REGISTRY


def test_default_tickers_matches_registry():
    assert set(DEFAULT_TICKERS) == set(TICKER_REGISTRY.keys())


def test_ticker_display():
    assert ticker_display("MSFT") == "Microsoft (MSFT)"
    assert ticker_display("UNKNOWN") == "UNKNOWN"


def test_tickers_by_category():
    groups = tickers_by_category()
    assert "CORE_INFRASTRUCTURE" in groups
    assert "CAT" in groups["CORE_INFRASTRUCTURE"]
    assert "BIG_TECH" in groups
    assert "AAPL" in groups["BIG_TECH"]
    assert "WALL_STREET_DARLINGS" in groups
    assert "SPY" in groups["WALL_STREET_DARLINGS"]
    assert "UBS_FUNDS" in groups
    assert "DVRUX" in groups["UBS_FUNDS"]


def test_no_midcap_in_defaults():
    """UBS Midcap must NOT be in default tickers unless validated."""
    for t in DEFAULT_TICKERS:
        name = TICKER_NAMES.get(t, "").lower()
        assert "midcap" not in name, f"Midcap ticker found in defaults: {t}"
