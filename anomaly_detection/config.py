"""Configuration for the anomaly detection system."""

import os

# ---------------------------------------------------------------------------
# Canonical Ticker Registry
# ---------------------------------------------------------------------------
# Each entry: ticker -> {name, category, is_fund, sector}
# Tickers use Yahoo Finance format (e.g., BRK-B not BRK.B).

TICKER_REGISTRY = {
    # =========================================================================
    # ENGINES OF THE REPUBLIC — The companies that build, feed, and defend America.
    # Selected for their irreplaceable role in physical infrastructure, food
    # supply chains, healthcare delivery, and financial plumbing.
    # See: the-companion-dossier.com/The_Watchtower
    # =========================================================================
    "CAT":   {"name": "Caterpillar",               "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Industrials"},
    "DE":    {"name": "Deere & Company",            "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Industrials"},
    "HON":   {"name": "Honeywell",                  "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Industrials"},
    "LMT":   {"name": "Lockheed Martin",            "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Defense"},
    "GE":    {"name": "GE Aerospace",               "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Industrials"},
    "WMT":   {"name": "Walmart",                    "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "COST":  {"name": "Costco",                     "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "HD":    {"name": "Home Depot",                  "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "JNJ":   {"name": "Johnson & Johnson",          "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Healthcare"},
    "PFE":   {"name": "Pfizer",                     "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Healthcare"},
    "ADM":   {"name": "Archer-Daniels-Midland",     "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "BG":    {"name": "Bunge Global",               "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "TSN":   {"name": "Tyson Foods",                "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Consumer Staples"},
    "SCHW":  {"name": "Charles Schwab",             "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Financials"},
    "BRK-B": {"name": "Berkshire Hathaway B",       "category": "ENGINES_OF_THE_REPUBLIC", "is_fund": False, "sector": "Financials"},

    # =========================================================================
    # CRITICAL CHOKE POINTS — Gatekeepers of energy, payments, logistics, tech,
    # and healthcare distribution. If these stop, the economy stops.
    # See: the-companion-dossier.com/The_Watchtower
    # =========================================================================
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

    # =========================================================================
    # BIG TECH — The companies shaping the future. Highest retail interest,
    # highest volatility, highest signal density.
    # =========================================================================
    "AAPL":  {"name": "Apple",                      "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},
    "NVDA":  {"name": "NVIDIA",                     "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},
    "META":  {"name": "Meta Platforms",             "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},
    "TSLA":  {"name": "Tesla",                      "category": "BIG_TECH", "is_fund": False, "sector": "Consumer Discretionary"},
    "NFLX":  {"name": "Netflix",                    "category": "BIG_TECH", "is_fund": False, "sector": "Communication Services"},
    "CRM":   {"name": "Salesforce",                 "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},
    "AMD":   {"name": "AMD",                        "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},
    "ORCL":  {"name": "Oracle",                     "category": "BIG_TECH", "is_fund": False, "sector": "Technology"},

    # =========================================================================
    # CONSUMER LEADERS — Brands that define American consumption. Defensive
    # plays with massive brand moats. If people are buying, these move.
    # =========================================================================
    "PG":    {"name": "Procter & Gamble",           "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Staples"},
    "KO":    {"name": "Coca-Cola",                  "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Staples"},
    "PEP":   {"name": "PepsiCo",                    "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Staples"},
    "MCD":   {"name": "McDonald's",                 "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Discretionary"},
    "NKE":   {"name": "Nike",                       "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Discretionary"},
    "SBUX":  {"name": "Starbucks",                  "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Discretionary"},
    "TGT":   {"name": "Target",                     "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Discretionary"},
    "LOW":   {"name": "Lowe's",                     "category": "CONSUMER_LEADERS", "is_fund": False, "sector": "Consumer Discretionary"},

    # =========================================================================
    # FINANCIAL TITANS — The banks, brokerages, and asset managers that move
    # money. When credit tightens or loosens, these are the first to know.
    # =========================================================================
    "GS":    {"name": "Goldman Sachs",              "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},
    "MS":    {"name": "Morgan Stanley",             "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},
    "BAC":   {"name": "Bank of America",            "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},
    "C":     {"name": "Citigroup",                  "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},
    "WFC":   {"name": "Wells Fargo",                "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},
    "BLK":   {"name": "BlackRock",                  "category": "FINANCIAL_TITANS", "is_fund": False, "sector": "Financials"},

    # =========================================================================
    # HEALTHCARE & PHARMA — The companies keeping people alive and the money
    # flowing through the healthcare-industrial complex.
    # =========================================================================
    "LLY":   {"name": "Eli Lilly",                  "category": "HEALTHCARE_PHARMA", "is_fund": False, "sector": "Healthcare"},
    "ABBV":  {"name": "AbbVie",                     "category": "HEALTHCARE_PHARMA", "is_fund": False, "sector": "Healthcare"},
    "MRK":   {"name": "Merck",                      "category": "HEALTHCARE_PHARMA", "is_fund": False, "sector": "Healthcare"},
    "AMGN":  {"name": "Amgen",                      "category": "HEALTHCARE_PHARMA", "is_fund": False, "sector": "Healthcare"},
    "BMY":   {"name": "Bristol-Myers Squibb",       "category": "HEALTHCARE_PHARMA", "is_fund": False, "sector": "Healthcare"},

    # =========================================================================
    # ENERGY & COMMODITIES — The oil majors and resource extractors. When
    # geopolitics moves, these move first.
    # =========================================================================
    "XOM":   {"name": "ExxonMobil",                 "category": "ENERGY_COMMODITIES", "is_fund": False, "sector": "Energy"},
    "CVX":   {"name": "Chevron",                    "category": "ENERGY_COMMODITIES", "is_fund": False, "sector": "Energy"},
    "COP":   {"name": "ConocoPhillips",             "category": "ENERGY_COMMODITIES", "is_fund": False, "sector": "Energy"},

    # =========================================================================
    # WALL STREET'S DARLINGS — The ETFs and index funds that Wall Street pushes
    # hardest. Vanguard, BlackRock, Invesco — the products they WANT you to buy.
    # THE SIGNAL watches these too.
    # =========================================================================
    "SPY":   {"name": "SPDR S&P 500 ETF",          "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "QQQ":   {"name": "Invesco QQQ (Nasdaq 100)",   "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "DIA":   {"name": "SPDR Dow Jones ETF",         "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "IWM":   {"name": "iShares Russell 2000",       "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "VTI":   {"name": "Vanguard Total Stock Market", "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "VOO":   {"name": "Vanguard S&P 500",           "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Index"},
    "ARKK":  {"name": "ARK Innovation ETF",         "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Thematic"},
    "VGT":   {"name": "Vanguard Info Tech ETF",     "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Technology"},
    "XLF":   {"name": "Financial Select SPDR",      "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Financials"},
    "XLE":   {"name": "Energy Select SPDR",         "category": "WALL_STREET_DARLINGS", "is_fund": True, "sector": "Energy"},

    # =========================================================================
    # THE CLERGY HOUSE — a Priest's bespoke collection. Curated picks outside
    # the standard taxonomy that the Signal still tracks for the house.
    # =========================================================================
    "ASTS":  {"name": "AST SpaceMobile",            "category": "CLERGY_HOUSE", "is_fund": False, "sector": "Communication Services"},
    "STM":   {"name": "STMicroelectronics",         "category": "CLERGY_HOUSE", "is_fund": False, "sector": "Technology"},

    # =========================================================================
    # RESERVE — Treasury proxy for risk-off benchmarking.
    # =========================================================================
    "BIL":   {"name": "SPDR Bloomberg 1-3 Month T-Bill", "category": "RESERVE", "is_fund": True, "sector": "Fixed Income"},

    # =========================================================================
    # UBS FUNDS — Managed fund positions for comparison.
    # =========================================================================
    "DVRUX": {"name": "UBS US Dividend Ruler P",    "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
    "QGRPX": {"name": "UBS US Quality Growth P",    "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
    "BNUEX": {"name": "UBS Intl Sustainable Equity P", "category": "UBS_FUNDS", "is_fund": True, "sector": "Fund"},
}

# Category display names & ordering
CATEGORY_LABELS = {
    "ENGINES_OF_THE_REPUBLIC": "Engines of the Republic",
    "CRITICAL_CHOKE_POINTS": "Critical Choke Points",
    "BIG_TECH": "Big Tech",
    "CONSUMER_LEADERS": "Consumer Leaders",
    "FINANCIAL_TITANS": "Financial Titans",
    "HEALTHCARE_PHARMA": "Healthcare & Pharma",
    "ENERGY_COMMODITIES": "Energy & Commodities",
    "WALL_STREET_DARLINGS": "Wall Street's Darlings",
    "CLERGY_HOUSE": "The Clergy House",
    "RESERVE": "Reserve",
    "UBS_FUNDS": "UBS Funds",
}

# Short tagline shown under each category heading on the dashboard.
CATEGORY_TAGLINES = {
    "CLERGY_HOUSE": "A Priest's bespoke collection.",
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
# THE SIGNAL anchors all detection and backtesting to a fixed historical
# start date rather than a sliding lookback window. This is what keeps the
# baseline stable: detectors fit against the same dataset every run, so
# verdicts on historical bars don't drift as time passes.
SIGNAL_START_DATE = "2024-11-01"
DEFAULT_LOOKBACK_DAYS = 365  # kept for API compatibility; superseded by SIGNAL_START_DATE
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
