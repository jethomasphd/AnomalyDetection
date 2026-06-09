"""Durable append-only storage for anomalies and signals.

Two layers, one truth:

  1. The LEDGER — newline-delimited JSON files under data/ledger/, committed
     to git by every automated run. This is the durable, human-auditable
     source of truth: append-only by convention, and *provably* append-only
     because git history shows every line ever added. A fresh checkout
     (every CI run) rebuilds the SQLite cache from the ledger, so watermarks
     and frozen verdicts genuinely survive between runs.

  2. SQLite — a fast local cache with uniqueness enforcement. Writes are
     append-only (INSERT OR IGNORE on unique keys): once a bar has been
     scored and written, its verdict is frozen so the backtest is
     reproducible and the anomaly log is an immutable audit trail.

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

Provenance marks how a row came to exist:
  - 'backfill': produced by the walk-forward simulation over history (the
    causal detectors guarantee the verdict equals what a live run that
    evening would have said; detected_at is set to the bar date).
  - 'live': produced by a scheduled run on a genuinely new bar.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

import pandas as pd

from .config import DB_PATH, LEDGER_DIR, MODEL_VERSION

logger = logging.getLogger(__name__)

ANOMALIES_LEDGER = "anomalies.jsonl"
SIGNALS_LEDGER = "signals.jsonl"
WATERMARKS_LEDGER = "watermarks.json"


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
    # Lightweight migrations for databases created before newer columns.
    for table in ("anomalies", "signals"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "detected_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN detected_at TEXT")
        if "provenance" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN provenance TEXT DEFAULT 'live'")
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
             detected_at, provenance, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = datetime.utcnow().isoformat() + "Z"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    params = []
    for r in rows:
        snapshot = r.get("features_snapshot")
        params.append((
            r["date"], r["ticker"], r["anomaly_type"],
            r.get("severity_score", 0),
            r.get("direction"),
            (snapshot if isinstance(snapshot, str) else json.dumps(snapshot)) if snapshot else None,
            r.get("model_version", MODEL_VERSION),
            json.dumps(r["threshold_params"]) if r.get("threshold_params") else None,
            r.get("detected_at", today),
            r.get("provenance", "live"),
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
             model_version, detected_at, provenance, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = datetime.utcnow().isoformat() + "Z"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    params = []
    for r in rows:
        rationale = r.get("rationale")
        params.append((
            r["date"], r["ticker"], r["signal"],
            r.get("confidence"),
            (rationale if isinstance(rationale, str) else json.dumps(rationale)) if rationale else None,
            r.get("model_version", MODEL_VERSION),
            r.get("detected_at", today),
            r.get("provenance", "live"),
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
# Ledger — the git-committed source of truth
# ---------------------------------------------------------------------------

# Stable field orders so exported lines are byte-identical run to run and
# git diffs show pure appends.
_ANOMALY_FIELDS = ["date", "ticker", "anomaly_type", "severity_score", "direction",
                   "features_snapshot", "model_version", "threshold_params",
                   "detected_at", "provenance"]
_SIGNAL_FIELDS = ["date", "ticker", "signal", "confidence", "rationale",
                  "model_version", "detected_at", "provenance"]


def export_ledger(db_path: str | None = None, ledger_dir: str | None = None) -> dict:
    """Write the full anomalies/signals/watermarks state to the ledger files.

    Rows are sorted by primary key so output is deterministic: a run that
    adds N rows produces a git diff of exactly N appended/interleaved lines.
    """
    ledger_dir = ledger_dir or LEDGER_DIR
    os.makedirs(ledger_dir, exist_ok=True)
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row

    counts = {}
    specs = [
        (ANOMALIES_LEDGER, "anomalies", _ANOMALY_FIELDS,
         "ORDER BY date, ticker, anomaly_type, model_version"),
        (SIGNALS_LEDGER, "signals", _SIGNAL_FIELDS,
         "ORDER BY date, ticker, model_version"),
    ]
    for fname, table, fields, order in specs:
        rows = conn.execute(f"SELECT * FROM {table} {order}").fetchall()
        path = os.path.join(ledger_dir, fname)
        with open(path, "w") as f:
            for r in rows:
                rec = {k: r[k] for k in fields}
                f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        counts[table] = len(rows)

    wm = {t: d for t, d in conn.execute(
        "SELECT ticker, last_date FROM bar_watermarks ORDER BY ticker").fetchall()}
    with open(os.path.join(ledger_dir, WATERMARKS_LEDGER), "w") as f:
        json.dump(wm, f, indent=2, sort_keys=True)
    counts["watermarks"] = len(wm)
    conn.close()

    logger.info("Ledger exported to %s: %s", ledger_dir, counts)
    return counts


def import_ledger(db_path: str | None = None, ledger_dir: str | None = None) -> dict:
    """Load ledger files into SQLite (INSERT OR IGNORE — frozen rows win)."""
    ledger_dir = ledger_dir or LEDGER_DIR
    counts = {"anomalies": 0, "signals": 0, "watermarks": 0}

    a_path = os.path.join(ledger_dir, ANOMALIES_LEDGER)
    if os.path.isfile(a_path):
        with open(a_path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        counts["anomalies"] = upsert_anomalies(rows, db_path=db_path)

    s_path = os.path.join(ledger_dir, SIGNALS_LEDGER)
    if os.path.isfile(s_path):
        with open(s_path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        counts["signals"] = upsert_signals(rows, db_path=db_path)

    w_path = os.path.join(ledger_dir, WATERMARKS_LEDGER)
    if os.path.isfile(w_path):
        with open(w_path) as f:
            wm = json.load(f)
        counts["watermarks"] = update_bar_watermarks(wm, db_path=db_path)

    logger.info("Ledger imported from %s: %s", ledger_dir, counts)
    return counts


def bootstrap_from_ledger(db_path: str | None = None, ledger_dir: str | None = None) -> bool:
    """If the SQLite cache is empty (fresh checkout), rebuild it from the ledger.

    Returns True if an import was performed. This is what makes the durable
    store actually durable on ephemeral CI runners: SQLite is disposable,
    the committed ledger is not.
    """
    existing = count_rows(db_path=db_path)
    has_watermarks = bool(get_bar_watermarks(db_path=db_path))
    if existing["anomalies"] or existing["signals"] or has_watermarks:
        return False
    ledger_dir = ledger_dir or LEDGER_DIR
    if not os.path.isdir(ledger_dir):
        return False
    import_ledger(db_path=db_path, ledger_dir=ledger_dir)
    return True


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


def get_signals_for_backtest(db_path: str | None = None) -> list[dict]:
    """Read ALL signal rows (no cap) with parsed rationale, oldest first.

    This is the backtest's input: the full immutable signal ledger, not the
    display-capped alerts.json. Each row carries date (the bar), detected_at
    (when the verdict existed), provenance, and the rationale details
    (deviation, trend value, etc.) frozen at detection time.
    """
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY date, ticker, model_version"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        rec = dict(r)
        if rec.get("rationale"):
            try:
                rec["rationale"] = json.loads(rec["rationale"])
            except (json.JSONDecodeError, TypeError):
                rec["rationale"] = {}
        else:
            rec["rationale"] = {}
        out.append(rec)
    return out


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


def reset_storage(db_path: str | None = None, ledger_dir: str | None = None) -> dict:
    """Wipe anomalies, signals, watermarks AND the committed ledger files.

    Used when the detection regime changes (e.g. v1 percentile thresholds ->
    v2 causal scoring) so old drifted verdicts don't contaminate the frozen
    log going forward. Returns counts of rows deleted for audit.
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

    ledger_dir = ledger_dir or LEDGER_DIR
    for fname in (ANOMALIES_LEDGER, SIGNALS_LEDGER, WATERMARKS_LEDGER):
        path = os.path.join(ledger_dir, fname)
        if os.path.isfile(path):
            os.remove(path)

    logger.warning(
        "Storage wiped: %d anomalies, %d signals, %d watermarks deleted (+ledger files)",
        a_count, s_count, w_count,
    )
    return {"anomalies_deleted": a_count, "signals_deleted": s_count,
            "watermarks_deleted": w_count}


# ---------------------------------------------------------------------------
# Conversion helpers: pipeline results -> storage rows
# ---------------------------------------------------------------------------

def results_to_anomaly_rows(
    results: pd.DataFrame,
    detected_at: str | None = None,
    provenance: str = "live",
) -> list[dict]:
    """Convert detection results DataFrame to anomaly storage rows.

    Only includes rows where consensus_anomaly is True.
    Creates one row per (date, ticker, method) that flagged.

    For provenance='live', `detected_at` is the run date (defaults to today
    UTC). For provenance='backfill', detected_at is set per-row to the BAR
    date: the causal detectors guarantee that is exactly the verdict a live
    run that evening would have produced.
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
        row_detected_at = date_str if provenance == "backfill" else detected_at
        dev_pct = r.get("deviation_pct", 0)
        direction = "above" if dev_pct > 0 else "below" if dev_pct < 0 else "neutral"

        features = {
            "close": float(r.get("Close", 0)),
            "volume": float(r.get("Volume", 0)),
            "daily_return": float(r.get("daily_return", 0)) if pd.notna(r.get("daily_return")) else 0,
            "deviation_pct": float(dev_pct),
            "dev_z": float(r.get("dev_z", 0)),
            "trajectory": r.get("trajectory", "stable"),
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
                    "detected_at": row_detected_at,
                    "provenance": provenance,
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
            "detected_at": row_detected_at,
            "provenance": provenance,
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
            "provenance": a.get("provenance", "live"),
        })
    return rows
