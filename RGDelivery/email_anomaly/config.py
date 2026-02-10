"""Configuration for the email click anomaly detection system."""

import os

# --- Data Settings ---
DEFAULT_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.csv")
MIN_DATA_POINTS = 30
MIN_DAILY_SENDS = 5000    # Minimum average daily sends to include a domain
MIN_DAILY_CLICKS = 500    # Minimum average daily clicks to include a domain

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

# --- Detection Method Weights (retuned for email per instructions.md) ---
# Matrix Profile increased (novelty detection critical for email)
# Fourier decreased (email has weaker cyclical structure)
METHOD_WEIGHTS = {
    "fourier": 0.15,
    "matrix_profile": 0.30,
    "ensemble": 0.30,
    "ewma": 0.25,
}

# --- EWMA Parameters ---
EWMA_SPAN = 20
EWMA_TREND_WINDOW = 5

# --- Matrix Profile Parameters ---
MP_SUBSEQUENCE_LENGTH = 7  # One week of email data

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
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
