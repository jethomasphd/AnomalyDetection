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
    # THE MEGA-CAP 100 — completion of the top 100 US-listed tickers by market
    # capitalization (measured via yfinance, 2026-06; the other top-100 names
    # already live in the thematic categories above). Includes US-listed ADRs.
    # =========================================================================
    "TSM":   {"name": "Taiwan Semiconductor (ADR)",  "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "AVGO":  {"name": "Broadcom",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "MU":    {"name": "Micron Technology",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "ASML":  {"name": "ASML Holding (ADR)",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "INTC":  {"name": "Intel",                       "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "CSCO":  {"name": "Cisco Systems",               "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "LRCX":  {"name": "Lam Research",                "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "AMAT":  {"name": "Applied Materials",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "ARM":   {"name": "Arm Holdings (ADR)",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "PLTR":  {"name": "Palantir",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "HSBC":  {"name": "HSBC Holdings (ADR)",         "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},
    "PM":    {"name": "Philip Morris",               "category": "MEGA_CAP_100", "is_fund": False, "sector": "Consumer Staples"},
    "NVS":   {"name": "Novartis (ADR)",              "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "KLAC":  {"name": "KLA Corporation",             "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "AZN":   {"name": "AstraZeneca (ADR)",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "BABA":  {"name": "Alibaba (ADR)",               "category": "MEGA_CAP_100", "is_fund": False, "sector": "Consumer Discretionary"},
    "RY":    {"name": "Royal Bank of Canada",        "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},
    "TXN":   {"name": "Texas Instruments",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "IBM":   {"name": "IBM",                         "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "DELL":  {"name": "Dell Technologies",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "RTX":   {"name": "RTX Corporation",             "category": "MEGA_CAP_100", "is_fund": False, "sector": "Defense"},
    "SHEL":  {"name": "Shell (ADR)",                 "category": "MEGA_CAP_100", "is_fund": False, "sector": "Energy"},
    "LIN":   {"name": "Linde",                       "category": "MEGA_CAP_100", "is_fund": False, "sector": "Materials"},
    "GEV":   {"name": "GE Vernova",                  "category": "MEGA_CAP_100", "is_fund": False, "sector": "Industrials"},
    "TM":    {"name": "Toyota Motor (ADR)",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Consumer Discretionary"},
    "MRVL":  {"name": "Marvell Technology",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "PANW":  {"name": "Palo Alto Networks",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "AXP":   {"name": "American Express",            "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},
    "QCOM":  {"name": "Qualcomm",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "TMUS":  {"name": "T-Mobile US",                 "category": "MEGA_CAP_100", "is_fund": False, "sector": "Communication Services"},
    "SAP":   {"name": "SAP (ADR)",                   "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "TTE":   {"name": "TotalEnergies (ADR)",         "category": "MEGA_CAP_100", "is_fund": False, "sector": "Energy"},
    "VZ":    {"name": "Verizon",                     "category": "MEGA_CAP_100", "is_fund": False, "sector": "Communication Services"},
    "ADI":   {"name": "Analog Devices",              "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "ANET":  {"name": "Arista Networks",             "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "NVO":   {"name": "Novo Nordisk (ADR)",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "TD":    {"name": "Toronto-Dominion Bank",       "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},
    "TJX":   {"name": "TJX Companies",               "category": "MEGA_CAP_100", "is_fund": False, "sector": "Consumer Discretionary"},
    "APH":   {"name": "Amphenol",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "TMO":   {"name": "Thermo Fisher Scientific",    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "DIS":   {"name": "Walt Disney",                 "category": "MEGA_CAP_100", "is_fund": False, "sector": "Communication Services"},
    "APP":   {"name": "AppLovin",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "CRWD":  {"name": "CrowdStrike",                 "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "T":     {"name": "AT&T",                        "category": "MEGA_CAP_100", "is_fund": False, "sector": "Communication Services"},
    "ABT":   {"name": "Abbott Laboratories",         "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "GILD":  {"name": "Gilead Sciences",             "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "WELL":  {"name": "Welltower",                   "category": "MEGA_CAP_100", "is_fund": False, "sector": "Real Estate"},
    "ISRG":  {"name": "Intuitive Surgical",          "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "ETN":   {"name": "Eaton",                       "category": "MEGA_CAP_100", "is_fund": False, "sector": "Industrials"},
    "BX":    {"name": "Blackstone",                  "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},
    "SHOP":  {"name": "Shopify",                     "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "UBER":  {"name": "Uber Technologies",           "category": "MEGA_CAP_100", "is_fund": False, "sector": "Technology"},
    "PLD":   {"name": "Prologis",                    "category": "MEGA_CAP_100", "is_fund": False, "sector": "Real Estate"},
    "DHR":   {"name": "Danaher",                     "category": "MEGA_CAP_100", "is_fund": False, "sector": "Healthcare"},
    "CB":    {"name": "Chubb",                       "category": "MEGA_CAP_100", "is_fund": False, "sector": "Financials"},

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
    "MEGA_CAP_100": "The Mega-Cap 100",
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

# --- Feed health & price-basis reconciliation ---
# A ticker whose last N closes are identical to the cent is treated as a
# frozen upstream feed: its new bars are excluded from the frozen record
# (they are re-scored once the feed moves) and the condition is surfaced
# in run health and on the dashboard.
STALE_FEED_MIN_BARS = 5
# Frozen ledger rows record dollar values at the price basis of the fetch
# that wrote them. When the current fetch's close for the SAME bar diverges
# from the frozen close by more than this fraction, a corporate action
# (split / large adjustment) is declared: frozen dollar values get
# basis-translated wherever they are compared against fresh prices.
# Routine dividend re-adjustments stay well inside this tolerance.
PRICE_BASIS_TOLERANCE = 0.02

# --- Signal materiality gate ---
# A tradable signal (BUY/SELL/LONG/SHORT) requires the price to be at least
# this far (in %) from its EWMA trend. Statistical anomalies below this
# threshold remain visible as WATCH but never become trade calls — this is
# what keeps a 0.1% wiggle in a T-bill ETF out of the trade ledger.
TRADE_MIN_ABS_DEVIATION_PCT = 1.0

# --- Backtest protocol: invest/divest portfolio model ---
# Capital starts 100% in a baseline portfolio. Entry signals INVEST a fixed
# slice from the baseline into the ticker at the next session's close after
# detected_at; the slice DIVESTS back to the baseline on the frozen trend
# target (BUY), on the first bearish signal for the ticker, or at the time
# stop. No shorts, ever — bearish signals only move capital out. If the
# baseline holds less than one slice, the signal is skipped (capital is
# conserved, not invented). The benchmark is the same capital left 100% in
# the baseline, so strategy-vs-benchmark is like-for-like by construction.
PORTFOLIO_CAPITAL = 100_000
BACKTEST_UNIT_DOLLARS = 10_000        # slice moved per invest signal
BACKTEST_COST_BPS_PER_SIDE = 5.0      # per stock transaction; baseline assumed frictionless
BACKTEST_MAX_HOLD_TRADING_DAYS = 30   # time-stop for every position
BACKTEST_BASELINE_TICKER = "SPY"      # where idle capital lives (and the benchmark)
BACKTEST_BENCHMARK_TICKER = BACKTEST_BASELINE_TICKER  # back-compat alias
# Which bullish signals invest. ("BUY",) = washout entries only;
# ("BUY", "LONG") would also invest on building-momentum entries. Set by the
# split-half robustness study (see HOW_IT_WORKS.md): adding LONG roughly
# doubles trade count, adds no excess return, and turns the first half of
# the window NEGATIVE vs baseline — BUY-only is positive in both halves
# under both baselines. LONG remains an informational momentum flag.
BACKTEST_ENTRY_SIGNALS = ("BUY",)

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
