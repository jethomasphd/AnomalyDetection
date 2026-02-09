"""Configuration for the anomaly detection system."""

import os

# --- Default Tickers ---
# A broad watchlist covering major stocks, ETFs, and sectors.
# Users can override via CLI or config file.
DEFAULT_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA",       # Major index ETFs
    "AAPL", "MSFT", "GOOGL", "AMZN",   # Big tech
    "NVDA", "META", "TSLA",             # Growth/momentum
    "JPM", "GS", "BAC",                 # Financials
    "XLE", "XLF", "XLV", "XLK",        # Sector ETFs
    "GLD", "TLT", "VIX",               # Macro indicators
]

# --- Data Settings ---
DEFAULT_LOOKBACK_DAYS = 365
MIN_DATA_POINTS = 30  # Minimum observations needed for detection

# --- Sensitivity Presets ---
# Maps to percentile thresholds for anomaly scoring.
# Higher percentile = fewer anomalies flagged (more conservative).
SENSITIVITY_PRESETS = {
    "low": {
        "percentile": 99.5,
        "z_threshold": 3.0,
        "description": "Only extreme anomalies — high confidence, few alerts",
    },
    "medium": {
        "percentile": 97.5,
        "z_threshold": 2.5,
        "description": "Balanced — catches meaningful moves without noise",
    },
    "high": {
        "percentile": 95.0,
        "z_threshold": 2.0,
        "description": "Sensitive — flags emerging patterns early",
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
EWMA_SPAN = 20  # ~1 trading month
EWMA_TREND_WINDOW = 5

# --- Matrix Profile Parameters ---
MP_SUBSEQUENCE_LENGTH = 10

# --- Fourier Parameters ---
FOURIER_TOP_K = 5  # Top frequency components to analyze

# --- Ensemble Weights ---
ENSEMBLE_WEIGHTS = {
    "zscore": 0.40,
    "seasonal": 0.30,
    "isolation_forest": 0.30,
}

# --- Output Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
