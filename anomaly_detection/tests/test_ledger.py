"""Ledger round-trip: the committed files must fully reconstitute the store.

This is the durability fix for ephemeral CI runners: SQLite is a cache,
the git-committed JSONL ledger is the truth. If export -> wipe -> import
loses anything, watermarks die between runs and the system silently
reverts to re-scoring history (the v1 failure mode).
"""

import os
import tempfile

import pytest

from anomaly_detection.config import MODEL_VERSION
from anomaly_detection.storage import (
    bootstrap_from_ledger,
    count_rows,
    export_ledger,
    get_all_anomalies,
    get_all_signals,
    get_bar_watermarks,
    import_ledger,
    update_bar_watermarks,
    upsert_anomalies,
    upsert_signals,
)


@pytest.fixture
def tmp_env():
    fd, db1 = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    fd, db2 = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    ledger = tempfile.mkdtemp()
    yield db1, db2, ledger
    for p in (db1, db2):
        if os.path.exists(p):
            os.unlink(p)


def _populate(db):
    upsert_anomalies([{
        "date": "2026-02-01", "ticker": "NVDA", "anomaly_type": "consensus",
        "severity_score": 0.81, "direction": "below",
        "features_snapshot": {"close": 800.5, "dev_z": -3.1},
        "model_version": MODEL_VERSION, "detected_at": "2026-02-01",
        "provenance": "backfill",
    }], db_path=db)
    upsert_signals([{
        "date": "2026-02-01", "ticker": "NVDA", "signal": "BUY",
        "confidence": "Strong",
        "rationale": {"description": "...", "details": {"ewma_value": 820.0}},
        "model_version": MODEL_VERSION, "detected_at": "2026-02-02",
        "provenance": "live",
    }], db_path=db)
    update_bar_watermarks({"NVDA": "2026-02-05", "AAPL": "2026-02-04"}, db_path=db)


def test_ledger_round_trip(tmp_env):
    db1, db2, ledger = tmp_env
    _populate(db1)
    counts = export_ledger(db_path=db1, ledger_dir=ledger)
    assert counts == {"anomalies": 1, "signals": 1, "watermarks": 2}

    import_ledger(db_path=db2, ledger_dir=ledger)
    assert count_rows(db_path=db2) == count_rows(db_path=db1)
    assert get_bar_watermarks(db_path=db2) == get_bar_watermarks(db_path=db1)

    a1, a2 = get_all_anomalies(db_path=db1)[0], get_all_anomalies(db_path=db2)[0]
    for field in ("date", "ticker", "anomaly_type", "severity_score",
                  "detected_at", "provenance", "features_snapshot"):
        assert a1[field] == a2[field], f"anomaly field {field} lost in round-trip"

    s1, s2 = get_all_signals(db_path=db1)[0], get_all_signals(db_path=db2)[0]
    for field in ("date", "ticker", "signal", "confidence", "detected_at",
                  "provenance", "rationale"):
        assert s1[field] == s2[field], f"signal field {field} lost in round-trip"


def test_bootstrap_only_fires_on_empty_store(tmp_env):
    db1, db2, ledger = tmp_env
    _populate(db1)
    export_ledger(db_path=db1, ledger_dir=ledger)

    # Fresh (empty) store: bootstrap imports.
    assert bootstrap_from_ledger(db_path=db2, ledger_dir=ledger) is True
    assert get_bar_watermarks(db_path=db2)["NVDA"] == "2026-02-05"

    # Populated store: bootstrap is a no-op (never clobbers local state).
    assert bootstrap_from_ledger(db_path=db2, ledger_dir=ledger) is False


def test_import_is_idempotent_and_frozen(tmp_env):
    db1, db2, ledger = tmp_env
    _populate(db1)
    export_ledger(db_path=db1, ledger_dir=ledger)

    import_ledger(db_path=db2, ledger_dir=ledger)
    before = count_rows(db_path=db2)
    import_ledger(db_path=db2, ledger_dir=ledger)  # second import: no dupes
    assert count_rows(db_path=db2) == before


def test_export_is_deterministic(tmp_env):
    db1, _, ledger = tmp_env
    _populate(db1)
    export_ledger(db_path=db1, ledger_dir=ledger)
    with open(os.path.join(ledger, "signals.jsonl")) as f:
        first = f.read()
    export_ledger(db_path=db1, ledger_dir=ledger)
    with open(os.path.join(ledger, "signals.jsonl")) as f:
        second = f.read()
    assert first == second, "ledger export must be byte-stable for clean git diffs"
