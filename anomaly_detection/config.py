"""Configuration for the anomaly detection system."""

import os

# ---------------------------------------------------------------------------
# Canonical Ticker Registry
# ---------------------------------------------------------------------------
# Each entry: ticker -> {name, category, is_fund, sector}
# Tickers use Yahoo Finance format (e.g., BRK-B not BRK.B).

TICKER_REGISTRY = {
    # --- ENGINES OF THE REPUBLIC ---
    "CAT":   {"name": "Caterpillar",               "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Industrials"},
    "DE":    {"name": "Deere & Company",            "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Industrials"},
    "HON":   {"name": "Honeywell",                  "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Industrials"},
    "LMT":   {"name": "Lockheed Martin",            "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Defense"},
    "GE":    {"name": "GE Aerospace",               "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Industrials"},
    "WMT":   {"name": "Walmart",                    "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "COST":  {"name": "Costco",                     "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "HD":    {"name": "Home Depot",                  "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "JNJ":   {"name": "Johnson & Johnson",          "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Healthcare"},
    "PFE":   {"name": "Pfizer",                     "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Healthcare"},
    "ADM":   {"name": "Archer-Daniels-Midland",     "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "BG":    {"name": "Bunge Global",               "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "TSN":   {"name": "Tyson Foods",                "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Consumer Staples"},
    "SCHW":  {"name": "Charles Schwab",             "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Financials"},
    "BRK-B": {"name": "Berkshire Hathaway B",       "category": "CORE_INFRASTRUCTURE", "is_fund": False, "sector": "Financials"},

    # --- CRITICAL CHOKE POINTS ---
    "NEE":   {"name": "NextEra Energy",             "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Utilities"},
    "D":     {"name": "Dominion Energy",            "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Utilities"},
    "KMI":   {"name": "Kinder Morgan",              "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Energy"},
    "WMB":   {"name": "Williams Companies",         "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Energy"},
    "V":     {"name": "Visa",                       "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Financials"},
    "MA":    {"name": "Mastercard",                  "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Financials"},
    "JPM":   {"name": "JPMorgan Chase",             "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Financials"},
    "MSFT":  {"name": "Microsoft",                  "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Technology"},
    "AMZN":  {"name": "Amazon",                     "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Technology"},
    "GOOGL": {"name": "Alphabet",                   "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Technology"},
    "UNP":   {"name": "Union Pacific",              "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Industrials"},
    "NSC":   {"name": "Norfolk Southern",           "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Industrials"},
    "MCK":   {"name": "McKesson",                   "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Healthcare"},
    "UNH":   {"name": "UnitedHealth Group",         "category": "CRITICAL_CHOKE_POINTS", "is_fund": False, "sector": "Healthcare"},

    # --- RESERVE ---
    "BIL":   {"name": "SPDR Bloomberg 1-3 Month T-Bill", "category": "RESERVE", "is_fund": True, "sector": "Fixed Income"},

    # --- BROAD INDEX ---
    "SPY":   {"name": "SPDR S&P 500 ETF",          "category": "BROAD_INDEX", "is_fund": True, "sector": "Index"},

    # --- UBS FUNDS ---
    "DVRUX": {"name": "UBS US Dividend Ruler P",    "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
    "QGRPX": {"name": "UBS US Quality Growth P",    "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
    "BNUEX": {"name": "UBS Intl Sustainable Equity P", "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
}

# Category display names & ordering
CATEGORY_LABELS = {
    "CORE_INFRASTRUCTURE": "Core Infrastructure",
    "CRITICAL_CHOKE_POINTS": "Critical Choke Points",
    "RESERVE": "Reserve",
    "BROAD_INDEX": "Broad Index",
    "UBS_FUNDS": "UBS Funds",
}

CATEGORY_ORDER = list(CATEGORY_LABELS.keys())


def get_default_tickers() -> list[str]:
    """Return the full list of default tickers from the registry."""
    return list(TICKER_REGISTRY.keys())


def tickers_by_category() -> dict[str, list[str]]:
    """Group tickers by category, respecting CATEGORY_ORDER."""
    groups: dict[str, list[str]] = {}
    for t, info in TICKER_REGISTRY.items():
        groups.setdefault(info["category"], []).append(t)
    return {cat: groups.get(cat, []) for cat in CATEGORY_ORDER if cat in groups}


# Backwards-compatible flat lookups
DEFAULT_TICKERS = get_default_tickers()
TICKER_NAMES = {t: info["name"] for t, info in TICKER_REGISTRY.items()}
TICKER_SECTORS = {t: info["sector"] for t, info in TICKER_REGISTRY.items()}


def ticker_display(ticker: str) -> str:
    """Return 'CompanyName (TICKER)' for display."""
    name = TICKER_NAMES.get(ticker)
    return f"{name} ({ticker})" if name else ticker


# --- Data Settings ---
DEFAULT_LOOKBACK_DAYS = 365
MIN_DATA_POINTS = 30

# --- Sensitivity Presets ---
SENSITIVITY_PRESETS = {
    "low": {
        "percentile": 99.5,
        "z_threshold": 3.0,
        "description": "Only extreme anomalies",
    },
    "medium": {
        "percentile": 97.5,
        "z_threshold": 2.5,
        "description": "Balanced detection",
    },
    "high": {
        "percentile": 95.0,
        "z_threshold": 2.0,
        "description": "Sensitive — catches early signals",
    },
}

DEFAULT_SENSITIVITY = os.environ.get("ANOMALY_SENSITIVITY", "medium")

# --- Detection Method Weights (for consensus score) ---
METHOD_WEIGHTS = {
    "fourier": 0.20,
    "matrix_profile": 0.25,
    "ensemble": 0.30,
    "ewma": 0.25,
}

# --- EWMA Parameters ---
EWMA_SPAN = 20
EWMA_TREND_WINDOW = 5

# --- Matrix Profile Parameters ---
MP_SUBSEQUENCE_LENGTH = 10

# --- Fourier Parameters ---
FOURIER_TOP_K = 5

# --- Ensemble Weights ---
ENSEMBLE_WEIGHTS = {
    "zscore": 0.40,
    "seasonal": 0.30,
    "isolation_forest": 0.30,
}

# --- Model version — bump when detection logic changes materially ---
MODEL_VERSION = "1.1.0"

# --- Output Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
DB_PATH = os.path.join(DATA_DIR, "anomaly_store.db")
