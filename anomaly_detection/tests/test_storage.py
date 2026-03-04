"""Tests for the idempotent storage layer."""

import os
import tempfile
import pytest

from anomaly_detection.storage import (
    _get_conn,
    upsert_anomalies,
    upsert_signals,
    count_rows,
    get_all_signals,
    get_all_anomalies,
    get_existing_dates,
)
from anomaly_detection.config import MODEL_VERSION


@pytest.fixture
def tmp_db():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _sample_anomaly_rows():
    return [
        {
            "date": "2026-01-15",
            "ticker": "MSFT",
            "anomaly_type": "consensus",
            "severity_score": 0.72,
            "direction": "below",
            "features_snapshot": {"close": 400, "deviation_pct": -5.2},
            "model_version": MODEL_VERSION,
        },
        {
            "date": "2026-01-15",
            "ticker": "MSFT",
            "anomaly_type": "ewma",
            "severity_score": 0.65,
            "direction": "below",
            "features_snapshot": {"close": 400},
            "model_version": MODEL_VERSION,
        },
    ]


def _sample_signal_rows():
    return [
        {
            "date": "2026-01-15",
            "ticker": "MSFT",
            "signal": "BUY",
            "confidence": "Moderate",
            "rationale": {"description": "Oversold"},
            "model_version": MODEL_VERSION,
        },
    ]


def test_upsert_anomalies_creates_rows(tmp_db):
    rows = _sample_anomaly_rows()
    n = upsert_anomalies(rows, db_path=tmp_db)
    assert n == 2
    counts = count_rows(db_path=tmp_db)
    assert counts["anomalies"] == 2


def test_upsert_anomalies_idempotent(tmp_db):
    """Re-inserting the same rows should not increase row count."""
    rows = _sample_anomaly_rows()
    upsert_anomalies(rows, db_path=tmp_db)
    counts_before = count_rows(db_path=tmp_db)

    # Re-insert same rows
    upsert_anomalies(rows, db_path=tmp_db)
    counts_after = count_rows(db_path=tmp_db)

    assert counts_before == counts_after


def test_upsert_signals_idempotent(tmp_db):
    """Re-inserting the same signal should not duplicate."""
    rows = _sample_signal_rows()
    upsert_signals(rows, db_path=tmp_db)
    counts_before = count_rows(db_path=tmp_db)

    upsert_signals(rows, db_path=tmp_db)
    counts_after = count_rows(db_path=tmp_db)

    assert counts_before == counts_after


def test_consecutive_days_preserved(tmp_db):
    """Adding new day should preserve previous day's data."""
    day1 = [{
        "date": "2026-01-15", "ticker": "GOOGL", "anomaly_type": "consensus",
        "severity_score": 0.5, "model_version": MODEL_VERSION,
    }]
    day2 = [{
        "date": "2026-01-16", "ticker": "GOOGL", "anomaly_type": "consensus",
        "severity_score": 0.6, "model_version": MODEL_VERSION,
    }]

    upsert_anomalies(day1, db_path=tmp_db)
    assert count_rows(db_path=tmp_db)["anomalies"] == 1

    upsert_anomalies(day2, db_path=tmp_db)
    assert count_rows(db_path=tmp_db)["anomalies"] == 2

    # Both dates should exist
    dates = get_existing_dates("GOOGL", db_path=tmp_db)
    assert "2026-01-15" in dates
    assert "2026-01-16" in dates


def test_get_existing_dates(tmp_db):
    rows = _sample_anomaly_rows()
    upsert_anomalies(rows, db_path=tmp_db)
    dates = get_existing_dates("MSFT", db_path=tmp_db)
    assert "2026-01-15" in dates
    assert len(dates) == 1


def test_get_all_signals(tmp_db):
    rows = _sample_signal_rows()
    upsert_signals(rows, db_path=tmp_db)
    signals = get_all_signals(db_path=tmp_db)
    assert len(signals) == 1
    assert signals[0]["ticker"] == "MSFT"
    assert signals[0]["signal"] == "BUY"


def test_empty_upsert(tmp_db):
    """Upserting empty list should be a no-op."""
    assert upsert_anomalies([], db_path=tmp_db) == 0
    assert upsert_signals([], db_path=tmp_db) == 0
