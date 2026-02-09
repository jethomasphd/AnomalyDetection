"""Main pipeline — orchestrates the full detection workflow.

Usage:
    python -m anomaly_detection.pipeline [options]
"""

import argparse
import json
import logging
import os
import sys

import pandas as pd

from .alerts import alerts_to_json, alerts_to_markdown, generate_alerts
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
    """Execute the full anomaly detection pipeline.

    Returns a summary dict with counts and paths.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Stage 1: Fetch data
    logger.info("=" * 60)
    logger.info("STAGE 1: Fetching stock data from Yahoo Finance")
    logger.info("=" * 60)
    raw_df = fetch_multiple(tickers=tickers, lookback_days=lookback_days)

    # Stage 2: Compute features
    logger.info("=" * 60)
    logger.info("STAGE 2: Computing features")
    logger.info("=" * 60)
    featured_df = compute_features(raw_df)

    # Save raw data
    raw_path = os.path.join(DATA_DIR, "stock_data.csv")
    featured_df.to_csv(raw_path, index=False)
    logger.info("Raw data saved to %s", raw_path)

    # Stage 3: Run detection engine
    logger.info("=" * 60)
    logger.info("STAGE 3: Running anomaly detection (4 methods)")
    logger.info("=" * 60)
    results = run_all(featured_df, sensitivity=sensitivity)

    # Save results
    results_path = os.path.join(DATA_DIR, "detection_results.csv")
    results.to_csv(results_path, index=False)
    logger.info("Detection results saved to %s", results_path)

    # Stage 4: Generate alerts
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating alerts")
    logger.info("=" * 60)
    alerts = generate_alerts(results)

    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    alerts_to_json(alerts, alerts_path)

    # Print markdown summary
    md = alerts_to_markdown(alerts)
    print("\n" + md)

    # Stage 5: Generate dashboard
    logger.info("=" * 60)
    logger.info("STAGE 5: Building dashboard")
    logger.info("=" * 60)
    dashboard_path = generate_dashboard(
        results,
        alerts,
        sensitivity=sensitivity,
        lookback_days=lookback_days,
    )

    summary = {
        "tickers_analyzed": int(results["Ticker"].nunique()),
        "total_observations": len(results),
        "anomalies_detected": int(results["consensus_anomaly"].sum()),
        "critical_alerts": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
        "high_alerts": sum(1 for a in alerts if a["severity"] == "HIGH"),
        "data_path": raw_path,
        "results_path": results_path,
        "alerts_path": alerts_path,
        "dashboard_path": dashboard_path,
    }

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("  Tickers: %d", summary["tickers_analyzed"])
    logger.info("  Observations: %d", summary["total_observations"])
    logger.info("  Anomalies: %d", summary["anomalies_detected"])
    logger.info("  Dashboard: %s", dashboard_path)
    logger.info("=" * 60)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Stock Anomaly Detection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (20 major tickers, medium sensitivity)
  python -m anomaly_detection.pipeline

  # Specific tickers
  python -m anomaly_detection.pipeline --tickers "AAPL,MSFT,GOOGL"

  # High sensitivity, 6-month lookback
  python -m anomaly_detection.pipeline --sensitivity high --lookback 180
        """,
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated list of tickers (default: built-in watchlist)",
    )
    parser.add_argument(
        "--sensitivity",
        type=str,
        choices=["low", "medium", "high"],
        default=DEFAULT_SENSITIVITY,
        help="Detection sensitivity (default: medium)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Days of historical data to analyze (default: 365)",
    )
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
