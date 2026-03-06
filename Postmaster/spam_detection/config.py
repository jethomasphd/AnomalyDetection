"""Configuration for the Google Spam Rate Anomaly Detection system.

"Feel the rhythm, feel the rhyme, get on up, it's bobsled time!"

Each detection method maps to a line from the Cool Runnings chant:
  Fourier Transform  -> "Feel the Rhythm"  (rhythm of spam rate changed)
  Matrix Profile     -> "Feel the Rhyme"   (unprecedented pattern detected)
  Statistical Ensemble -> "Get on Up"      (3 independent tests agree)
  EWMA Trend         -> "It's Bobsled Time" (momentum is locked in)
"""

import os

# --- Data Settings ---
DEFAULT_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Postmaster.csv")
DEFAULT_DATA_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.csv")
MIN_DATA_POINTS = 30  # Minimum days of data to include a domain
VALID_REPUTATIONS = ("MEDIUM", "HIGH")  # Only analyze domains with these reputations

# --- Sensitivity Presets ---
SENSITIVITY_PRESETS = {
    "low": {
        "percentile": 99.5,
        "z_threshold": 3.0,
        "description": "Only extreme anomalies — very few alerts",
    },
    "medium": {
        "percentile": 97.5,
        "z_threshold": 2.5,
        "description": "Balanced detection — catches real problems without too much noise",
    },
    "high": {
        "percentile": 95.0,
        "z_threshold": 2.0,
        "description": "Sensitive — catches early signals, more alerts",
    },
}

DEFAULT_SENSITIVITY = os.environ.get("ANOMALY_SENSITIVITY", "medium")

# --- Detection Method Weights ---
# Matrix Profile is weighted highest — "never seen this pattern before"
# is the single most important signal for spam rate monitoring.
# Fourier is weighted lowest — spam rate has weaker cyclical structure than clicks.
METHOD_WEIGHTS = {
    "fourier": 0.15,         # "Feel the Rhythm"
    "matrix_profile": 0.30,  # "Feel the Rhyme"
    "ensemble": 0.30,        # "Get on Up"
    "ewma": 0.25,            # "It's Bobsled Time"
}

# --- EWMA Parameters ---
EWMA_SPAN = 20          # 20-day exponential moving average
EWMA_TREND_WINDOW = 5   # 5-day window for trajectory classification

# --- Matrix Profile Parameters ---
MP_SUBSEQUENCE_LENGTH = 7  # One week of daily data

# --- Fourier Parameters ---
FOURIER_WINDOW = 30  # 30-day sliding window
FOURIER_TOP_K = 5    # Top-5 frequency components

# --- Ensemble Weights ---
ENSEMBLE_WEIGHTS = {
    "zscore": 0.40,
    "seasonal": 0.30,
    "isolation_forest": 0.30,
}

# --- Google Spam Rate Thresholds (industry reference) ---
# These are Google's published guidelines for spam rate health.
GOOGLE_THRESHOLDS = {
    "good": 0.001,      # < 0.1% — healthy
    "monitor": 0.003,   # < 0.3% — within tolerance but watch it
    "concern": 0.005,   # < 0.5% — needs attention
    "problem": 0.01,    # < 1.0% — serious problem
    "critical": 0.03,   # > 3.0% — deliverability at risk
}

# --- Output Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
