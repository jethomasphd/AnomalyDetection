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

from .alerts import alerts_to_json, alerts_to_markdown, generate_alerts, load_previous_alerts, merge_alerts
from .config import DATA_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_SENSITIVITY, DEFAULT_TICKERS, DOCS_DIR
from .data_fetch import compute_features, fetch_multiple
from .detection.engine import run_all
from .visualization.dashboard import generate_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(
    tickers: list[str] | None = None,
    sensitivity: str = DEFAULT_SENSITIVITY,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    """Execute the full anomaly detection pipeline."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

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

    # Stage 4: Signals (incremental — merge with previous run)
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating trading signals (incremental)")
    logger.info("=" * 60)
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    previous_alerts = load_previous_alerts(alerts_path)
    new_alerts = generate_alerts(results)
    alerts = merge_alerts(new_alerts, previous_alerts)
    alerts_to_json(alerts, alerts_path)
    print("\n" + alerts_to_markdown(alerts))

    # Build summary
    summary = {
        "run_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "tickers_analyzed": int(results["Ticker"].nunique()),
        "total_observations": len(results),
        "anomalies_detected": int(results["consensus_anomaly"].sum()),
        "actionable_signals": sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE")),
        "total_signals": len(alerts),
        "sensitivity": sensitivity,
        "lookback_days": lookback_days,
    }

    # Stage 5: Dashboard
    logger.info("=" * 60)
    logger.info("STAGE 5: Building dashboard")
    logger.info("=" * 60)
    dashboard_path = generate_dashboard(
        results, alerts,
        sensitivity=sensitivity,
        lookback_days=lookback_days,
    )

    summary["dashboard_path"] = dashboard_path

    logger.info("=" * 60)
    logger.info("DONE  |  %d tickers  |  %d anomalies  |  %d signals  |  %s",
                summary["tickers_analyzed"], summary["anomalies_detected"],
                summary["total_signals"], dashboard_path)
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
