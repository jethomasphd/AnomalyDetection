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
# z_threshold is the causal robust-z a method's score must exceed to flag.
# `percentile` is retained for backwards compatibility with old callers but
# is no longer used by the v2 causal detectors.
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

# --- Causal scoring scale ---
# Method scores are standardized robust-z values mapped onto [0, 1] by
# score = min(max(z, 0) / Z_SCORE_CAP, 1).  The scale is therefore directly
# interpretable: 0.50 = 2 sigma, 0.625 = 2.5 sigma, 1.0 = 4+ sigma.
Z_SCORE_CAP = 4.0

# Warmup: number of bars a detector observes before it may flag anything.
# Scores during warmup are 0 (insufficient history to standardize against).
CAUSAL_WARMUP_BARS = 60

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
# Rolling window used to standardize the EWMA deviation per ticker (the
# deviation is divided by its own trailing volatility, so thresholds adapt
# to each ticker's scale: BIL and NVDA are judged against themselves).
EWMA_DEV_VOL_WINDOW = 60
EWMA_DEV_VOL_MIN_PERIODS = 20
# Trajectory classification (units: sigma of standardized deviation per day).
TRAJECTORY_SLOPE_SIGMA_PER_DAY = 0.15
# |dev_z| above (z_threshold + this margin) classifies as breakout.
BREAKOUT_SIGMA_MARGIN = 1.0

# --- Matrix Profile Parameters ---
MP_SUBSEQUENCE_LENGTH = 10

# --- Fourier Parameters ---
FOURIER_TOP_K = 5
FOURIER_WINDOW = 60

# --- Ensemble Weights ---
ENSEMBLE_WEIGHTS = {
    "zscore": 0.40,
    "seasonal": 0.30,
    "isolation_forest": 0.30,
}
# Walk-forward Isolation Forest: refit cadence and training lookback (bars).
IFOREST_REFIT_EVERY = 21
IFOREST_TRAIN_WINDOW = 250
# Causal seasonal decomposition (additive): trailing trend window and period.
SEASONAL_PERIOD = 5
SEASONAL_TREND_WINDOW = 20

# --- Signal materiality gate ---
# A tradable signal (BUY/SELL/LONG/SHORT) requires the price to be at least
# this far (in %) from its EWMA trend. Statistical anomalies below this
# threshold remain visible as WATCH but never become trade calls — this is
# what keeps a 0.1% wiggle in a T-bill ETF out of the trade ledger.
TRADE_MIN_ABS_DEVIATION_PCT = 1.0

# --- Backtest protocol ---
# Signals are produced after the close of detected_at; fills happen at the
# next session's close. No same-bar fills, ever.
BACKTEST_UNIT_DOLLARS = 10_000
BACKTEST_COST_BPS_PER_SIDE = 5.0      # one-way transaction cost, basis points
BACKTEST_MAX_HOLD_TRADING_DAYS = 30   # time-stop for every position
BACKTEST_BENCHMARK_TICKER = "SPY"
# Long-only book: BUY/LONG open positions; SELL/SHORT act purely as exit
# triggers (close longs on their ticker) — matching their dashboard meaning
# of "take profits / tighten stops". Set by the measured edge: extreme
# below-trend stretches rebound (+2.3%/10 bars avg) while above-trend
# stretches show ~no drift, so the short side has no edge to harvest; the
# split-half study confirmed shorts only subtract (both-sides book went
# NEGATIVE in the second half; long-only stayed positive in both). Flip to
# False to simulate both sides. See HOW_IT_WORKS.md "Why long-only".
BACKTEST_LONG_ONLY = True

# --- Model version — bump when detection logic changes materially ---
# 2.0.0: causal detection regime. Every score at bar t uses only data
# through bar t; the historical backfill is therefore a true walk-forward
# simulation and live operation is identical to the backtest by construction.
MODEL_VERSION = "2.0.0"

# --- Output Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
DB_PATH = os.path.join(DATA_DIR, "anomaly_store.db")

# The committed, git-versioned source of truth for the append-only record.
# SQLite is a fast local cache rebuilt from these files on a fresh checkout;
# the ledger (and its git history) is the durable audit trail.
LEDGER_DIR = os.path.join(DATA_DIR, "ledger")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
