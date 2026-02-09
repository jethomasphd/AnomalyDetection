"""Configuration for the anomaly detection system."""

import os

# --- Default Tickers ---
DEFAULT_TICKERS = [
    "ZIP", "KELYA", "ASGN", "MAN",     # Staffing & recruitment
    "^GSPC", "^NDX",                    # Market benchmarks
    "TTD", "META", "GOOGL",             # Advertising / LLM-adjacent platforms
    "NVDA", "MSFT",                     # AI infrastructure
]

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

# --- Output Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
