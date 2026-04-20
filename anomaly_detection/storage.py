"""Durable append-only storage for anomalies and signals.

Uses SQLite for simplicity and portability. Writes are append-only
(INSERT OR IGNORE on unique keys): once a bar has been scored and written,
its verdict is frozen so the backtest is reproducible and the anomaly log is
an immutable audit trail.

Schema:
  anomalies:       (date, ticker, anomaly_type, model_version) is unique
  signals:         (date, ticker, model_version) is unique
  bar_watermarks:  ticker -> last_date scored (edge-only detection cursor)

Two timestamps on each row serve distinct purposes:
  - detected_at: the run date on which the verdict was produced. This is the
    date a portfolio manager would have actually seen the signal — the
    correct anchor for backtest trade entries (no peeking at the future).
  - created_at: SQL insertion time. Infrastructure timestamp, not a
    business-meaningful event.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

import pandas as pd

from .config import DB_PATH, MODEL_VERSION

logger = logging.getLogger(__name__)


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the SQLite database."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist, and add detected_at if missing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS anomalies (
            date            TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            anomaly_type    TEXT NOT NULL,
            severity_score  REAL,
            direction       TEXT,
            features_snapshot TEXT,  -- JSON blob
            model_version   TEXT NOT NULL,
            threshold_params TEXT,   -- JSON blob
            detected_at     TEXT,    -- run date (YYYY-MM-DD) the verdict was produced
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (date, ticker, anomaly_type, model_version)
        );

        CREATE TABLE IF NOT EXISTS signals (
            date            TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            signal          TEXT NOT NULL,
            confidence      TEXT,
            rationale       TEXT,    -- JSON blob
            model_version   TEXT NOT NULL,
            detected_at     TEXT,    -- run date (YYYY-MM-DD) the signal fired
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (date, ticker, model_version)
        );

        CREATE INDEX IF NOT EXISTS idx_anomalies_ticker_date
            ON anomalies(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_signals_ticker_date
            ON signals(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_signals_date
            ON signals(date DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_detected_at
            ON signals(detected_at);

        CREATE TABLE IF NOT EXISTS bar_watermarks (
            ticker     TEXT PRIMARY KEY,
            last_date  TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    # Lightweight migration for databases created before detected_at existed.
    for table in ("anomalies", "signals"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "detected_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN detected_at TEXT")
    conn.commit()


# ---------------------------------------------------------------------------
# Anomaly writes
# ---------------------------------------------------------------------------

def upsert_anomalies(rows: list[dict], db_path: str | None = None) -> int:
    """Append anomaly rows (INSERT OR IGNORE — never overwrites an existing
    (date, ticker, anomaly_type, model_version)). Returns rows newly inserted.

    Each row must have: date, ticker, anomaly_type, severity_score.
    Optional: direction, features_snapshot, model_version, threshold_params.
    """
    if not rows:
        return 0
    conn = _get_conn(db_path)
    sql = """
        INSERT OR IGNORE INTO anomalies
            (date, ticker, anomaly_type, severity_score, direction,
             features_snapshot, model_version, threshold_params,
             detected_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = datetime.utcnow().isoformat() + "Z"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    params = []
    for r in rows:
        params.append((
            r["date"], r["ticker"], r["anomaly_type"],
            r.get("severity_score", 0),
            r.get("direction"),
            json.dumps(r["features_snapshot"]) if r.get("features_snapshot") else None,
            r.get("model_version", MODEL_VERSION),
            json.dumps(r["threshold_params"]) if r.get("threshold_params") else None,
            r.get("detected_at", today),
            now,
        ))
    cur = conn.executemany(sql, params)
    conn.commit()
    inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(params)
    conn.close()
    logger.info("Appended %d anomaly rows (%d attempted)", inserted, len(params))
    return inserted


def upsert_signals(rows: list[dict], db_path: str | None = None) -> int:
    """Append signal rows (INSERT OR IGNORE — frozen once written)."""
    if not rows:
        return 0
    conn = _get_conn(db_path)
    sql = """
        INSERT OR IGNORE INTO signals
            (date, ticker, signal, confidence, rationale,
             model_version, detected_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = datetime.utcnow().isoformat() + "Z"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    params = []
    for r in rows:
        params.append((
            r["date"], r["ticker"], r["signal"],
            r.get("confidence"),
            json.dumps(r["rationale"]) if r.get("rationale") else None,
            r.get("model_version", MODEL_VERSION),
            r.get("detected_at", today),
            now,
        ))
    cur = conn.executemany(sql, params)
    conn.commit()
    inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(params)
    conn.close()
    logger.info("Appended %d signal rows (%d attempted)", inserted, len(params))
    return inserted


# ---------------------------------------------------------------------------
# Bar watermarks — edge-only detection cursor
# ---------------------------------------------------------------------------

def get_bar_watermarks(db_path: str | None = None) -> dict[str, str]:
    """Return {ticker: last_date_scored} for every ticker that has been seen.

    Used by the pipeline to detect anomalies only on bars strictly newer than
    the watermark, so historical verdicts are never recomputed.
    """
    conn = _get_conn(db_path)
    rows = conn.execute("SELECT ticker, last_date FROM bar_watermarks").fetchall()
    conn.close()
    return {t: d for t, d in rows}


def update_bar_watermarks(watermarks: dict[str, str], db_path: str | None = None) -> int:
    """Advance watermarks to the given {ticker: date}. Never moves backwards."""
    if not watermarks:
        return 0
    conn = _get_conn(db_path)
    now = datetime.utcnow().isoformat() + "Z"
    sql = """
        INSERT INTO bar_watermarks (ticker, last_date, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            last_date = excluded.last_date,
            updated_at = excluded.updated_at
        WHERE excluded.last_date > bar_watermarks.last_date
    """
    params = [(t, d, now) for t, d in watermarks.items()]
    conn.executemany(sql, params)
    conn.commit()
    conn.close()
    return len(params)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_existing_dates(ticker: str, db_path: str | None = None) -> set[str]:
    """Return the set of dates already stored for a ticker (anomalies table)."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT date FROM anomalies WHERE ticker = ?", (ticker,)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def get_all_signals(limit: int = 500, db_path: str | None = None) -> list[dict]:
    """Read all signals ordered by date desc, up to limit."""
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY date DESC, ticker LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_anomalies(limit: int = 5000, db_path: str | None = None) -> list[dict]:
    """Read all anomalies ordered by date desc."""
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM anomalies ORDER BY date DESC, ticker LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_anomalies_for_ticker(ticker: str, days: int = 90,
                             db_path: str | None = None) -> pd.DataFrame:
    """Return anomalies for a ticker as a DataFrame."""
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """SELECT * FROM anomalies
           WHERE ticker = ? AND date >= date('now', ?)
           ORDER BY date""",
        conn, params=(ticker, f"-{days} days")
    )
    conn.close()
    return df


def get_signals_for_ticker(ticker: str, days: int = 90,
                           db_path: str | None = None) -> pd.DataFrame:
    """Return signals for a ticker as a DataFrame."""
    conn = _get_conn(db_path)
    df = pd.read_sql_query(
        """SELECT * FROM signals
           WHERE ticker = ? AND date >= date('now', ?)
           ORDER BY date""",
        conn, params=(ticker, f"-{days} days")
    )
    conn.close()
    return df


def count_rows(db_path: str | None = None) -> dict:
    """Return row counts for integrity checks."""
    conn = _get_conn(db_path)
    a_count = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    s_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    return {"anomalies": a_count, "signals": s_count}


def reset_storage(db_path: str | None = None) -> dict:
    """Wipe anomalies, signals, and watermarks. Used when the detection
    regime changes (e.g. switching from a sliding window to a fixed anchor)
    so old drifted verdicts don't contaminate the frozen log going forward.

    Returns counts of rows deleted for audit.
    """
    conn = _get_conn(db_path)
    a_count = conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    s_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    w_count = conn.execute("SELECT COUNT(*) FROM bar_watermarks").fetchone()[0]
    conn.executescript("""
        DELETE FROM anomalies;
        DELETE FROM signals;
        DELETE FROM bar_watermarks;
    """)
    conn.commit()
    conn.close()
    logger.warning(
        "Storage wiped: %d anomalies, %d signals, %d watermarks deleted",
        a_count, s_count, w_count,
    )
    return {"anomalies_deleted": a_count, "signals_deleted": s_count,
            "watermarks_deleted": w_count}


# ---------------------------------------------------------------------------
# Conversion helpers: pipeline results -> storage rows
# ---------------------------------------------------------------------------

def results_to_anomaly_rows(results: pd.DataFrame, detected_at: str | None = None) -> list[dict]:
    """Convert detection results DataFrame to anomaly storage rows.

    Only includes rows where consensus_anomaly is True.
    Creates one row per (date, ticker, method) that flagged.
    `detected_at` defaults to today (UTC) and marks the run-date on which the
    verdict was produced — distinct from the bar's `date`.
    """
    anomalies = results[results.get("consensus_anomaly", False) == True].copy()
    if anomalies.empty:
        return []

    detected_at = detected_at or datetime.utcnow().strftime("%Y-%m-%d")

    rows = []
    method_cols = {
        "fourier_anomaly": ("fourier", "fourier_score"),
        "mp_anomaly": ("matrix_profile", "mp_score"),
        "ensemble_anomaly": ("ensemble", "ensemble_score"),
        "ewma_anomaly": ("ewma", "ewma_score"),
    }

    for _, r in anomalies.iterrows():
        date_str = r["Date"].strftime("%Y-%m-%d") if hasattr(r["Date"], "strftime") else str(r["Date"])
        dev_pct = r.get("deviation_pct", 0)
        direction = "above" if dev_pct > 0 else "below" if dev_pct < 0 else "neutral"

        features = {
            "close": float(r.get("Close", 0)),
            "volume": float(r.get("Volume", 0)),
            "daily_return": float(r.get("daily_return", 0)) if pd.notna(r.get("daily_return")) else 0,
            "deviation_pct": float(dev_pct),
            "trajectory": r.get("trajectory", "normal"),
            "consensus_score": float(r.get("consensus_score", 0)),
            "methods_flagged": int(r.get("methods_flagged", 0)),
        }

        # One row per flagging method
        for flag_col, (atype, score_col) in method_cols.items():
            if r.get(flag_col, False):
                rows.append({
                    "date": date_str,
                    "ticker": r["Ticker"],
                    "anomaly_type": atype,
                    "severity_score": float(r.get(score_col, 0)),
                    "direction": direction,
                    "features_snapshot": features,
                    "model_version": MODEL_VERSION,
                    "detected_at": detected_at,
                })

        # Also store the consensus anomaly itself
        rows.append({
            "date": date_str,
            "ticker": r["Ticker"],
            "anomaly_type": "consensus",
            "severity_score": float(r.get("consensus_score", 0)),
            "direction": direction,
            "features_snapshot": features,
            "model_version": MODEL_VERSION,
            "detected_at": detected_at,
        })

    return rows


def alerts_to_signal_rows(alerts: list[dict]) -> list[dict]:
    """Convert alert dicts to signal storage rows."""
    rows = []
    for a in alerts:
        rows.append({
            "date": a["date"],
            "ticker": a["ticker"],
            "signal": a["signal"],
            "confidence": a.get("confidence"),
            "rationale": {
                "description": a.get("description", ""),
                "consensus_score": a.get("consensus_score", 0),
                "methods_flagged": a.get("methods_flagged", 0),
                "details": a.get("details", {}),
            },
            "model_version": MODEL_VERSION,
            # first_detected is the alert's run-date of first appearance; fall
            # back to the bar date for legacy alerts that lack it.
            "detected_at": a.get("first_detected") or a.get("run_date") or a.get("date"),
        })
    return rows
