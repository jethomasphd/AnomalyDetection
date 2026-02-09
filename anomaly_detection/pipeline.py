"""Main pipeline — orchestrates the full detection workflow.

Usage:
    python -m anomaly_detection.pipeline [options]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

from .alerts import alerts_to_json, alerts_to_markdown, generate_alerts
from .config import DATA_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_SENSITIVITY, DEFAULT_TICKERS, DOCS_DIR, HISTORY_DIR
from .data_fetch import compute_features, fetch_multiple
from .detection.engine import run_all
from .visualization.dashboard import generate_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- History management ---

def _load_history() -> list[dict]:
    """Load all historical run summaries from data/history/."""
    index_path = os.path.join(HISTORY_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            return json.load(f)
    return []


def _save_history(history: list[dict]) -> None:
    """Save the history index."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    index_path = os.path.join(HISTORY_DIR, "index.json")
    with open(index_path, "w") as f:
        json.dump(history, f, indent=2)


def _save_run_snapshot(run_date: str, alerts: list[dict], summary: dict) -> None:
    """Save a snapshot of this run's alerts for historical tracking."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    snapshot = {
        "run_date": run_date,
        "summary": summary,
        "alerts": alerts,
    }
    snapshot_path = os.path.join(HISTORY_DIR, f"run_{run_date}.json")
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)


# --- Main pipeline ---

def run(
    tickers: list[str] | None = None,
    sensitivity: str = DEFAULT_SENSITIVITY,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    """Execute the full anomaly detection pipeline."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Stage 1: Fetch
    logger.info("=" * 60)
    logger.info("STAGE 1: Fetching stock data")
    logger.info("=" * 60)
    raw_df = fetch_multiple(tickers=tickers, lookback_days=lookback_days)

    # Stage 2: Features
    logger.info("=" * 60)
    logger.info("STAGE 2: Computing features")
    logger.info("=" * 60)
    featured_df = compute_features(raw_df)
    featured_df.to_csv(os.path.join(DATA_DIR, "stock_data.csv"), index=False)

    # Stage 3: Detection
    logger.info("=" * 60)
    logger.info("STAGE 3: Running anomaly detection (4 methods)")
    logger.info("=" * 60)
    results = run_all(featured_df, sensitivity=sensitivity)
    results.to_csv(os.path.join(DATA_DIR, "detection_results.csv"), index=False)

    # Stage 4: Alerts
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating alerts")
    logger.info("=" * 60)
    alerts = generate_alerts(results)
    alerts_to_json(alerts, os.path.join(DATA_DIR, "alerts.json"))
    print("\n" + alerts_to_markdown(alerts))

    # Build summary
    summary = {
        "run_date": run_date,
        "tickers_analyzed": int(results["Ticker"].nunique()),
        "total_observations": len(results),
        "anomalies_detected": int(results["consensus_anomaly"].sum()),
        "critical_alerts": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
        "high_alerts": sum(1 for a in alerts if a["severity"] == "HIGH"),
        "sensitivity": sensitivity,
        "lookback_days": lookback_days,
    }

    # Stage 5: History
    logger.info("=" * 60)
    logger.info("STAGE 5: Updating history")
    logger.info("=" * 60)
    history = _load_history()
    # Replace if same date already exists, otherwise append
    history = [h for h in history if h.get("run_date") != run_date]
    history.append(summary)
    history.sort(key=lambda h: h["run_date"])
    _save_history(history)
    _save_run_snapshot(run_date, alerts, summary)
    logger.info("History updated: %d total runs", len(history))

    # Stage 6: Dashboard
    logger.info("=" * 60)
    logger.info("STAGE 6: Building dashboard")
    logger.info("=" * 60)
    dashboard_path = generate_dashboard(
        results, alerts,
        sensitivity=sensitivity,
        lookback_days=lookback_days,
        history_data=history,
    )

    summary["dashboard_path"] = dashboard_path

    logger.info("=" * 60)
    logger.info("DONE  |  %d tickers  |  %d anomalies  |  %s",
                summary["tickers_analyzed"], summary["anomalies_detected"], dashboard_path)
    logger.info("=" * 60)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Stock Anomaly Detection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m anomaly_detection                               # defaults
  python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL"   # specific tickers
  python -m anomaly_detection --sensitivity high --lookback 180
        """,
    )
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated tickers (default: built-in watchlist)")
    parser.add_argument("--sensitivity", type=str, choices=["low", "medium", "high"],
                        default=DEFAULT_SENSITIVITY)
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="Days of historical data (default: 365)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    try:
        summary = run(tickers=tickers, sensitivity=args.sensitivity, lookback_days=args.lookback)
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
