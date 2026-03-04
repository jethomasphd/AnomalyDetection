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
from .config import DATA_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_SENSITIVITY, DEFAULT_TICKERS, DOCS_DIR, MODEL_VERSION
from .data_fetch import compute_features, fetch_multiple
from .detection.engine import run_all
from .storage import (
    alerts_to_signal_rows,
    count_rows,
    results_to_anomaly_rows,
    upsert_anomalies,
    upsert_signals,
)
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
    skip_validation: bool = False,
) -> dict:
    """Execute the full anomaly detection pipeline."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Stage 0: Ticker validation (optional, skipped in CI for speed)
    effective_tickers = tickers
    validation_failures = []
    if not skip_validation and tickers is None:
        logger.info("=" * 60)
        logger.info("STAGE 0: Validating default tickers via yfinance")
        logger.info("=" * 60)
        from .ticker_validation import validate_all_tickers
        vresult = validate_all_tickers()
        effective_tickers = vresult["valid"] or DEFAULT_TICKERS
        validation_failures = vresult["invalid"]
        if validation_failures:
            logger.warning("Excluding %d tickers that failed validation: %s",
                           len(validation_failures),
                           [f["ticker"] for f in validation_failures])
    elif tickers is None:
        effective_tickers = DEFAULT_TICKERS

    # Stage 1: Fetch
    logger.info("=" * 60)
    logger.info("STAGE 1: Fetching stock data")
    logger.info("=" * 60)
    raw_df = fetch_multiple(tickers=effective_tickers, lookback_days=lookback_days)

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

    # Stage 3b: Persist anomalies to durable store (idempotent upsert)
    logger.info("Persisting anomalies to SQLite store ...")
    anomaly_rows = results_to_anomaly_rows(results)
    upsert_anomalies(anomaly_rows)
    store_counts = count_rows()
    logger.info("Store now has %d anomaly rows, %d signal rows",
                store_counts["anomalies"], store_counts["signals"])

    # Stage 4: Signals (incremental — merge with previous run)
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating trading signals (incremental)")
    logger.info("=" * 60)
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    previous_alerts = load_previous_alerts(alerts_path)
    new_alerts = generate_alerts(results)
    alerts = merge_alerts(new_alerts, previous_alerts)
    alerts_to_json(alerts, alerts_path)

    # Persist signals to durable store
    signal_rows = alerts_to_signal_rows(alerts)
    upsert_signals(signal_rows)

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
        "model_version": MODEL_VERSION,
        "validation_failures": validation_failures,
    }

    # Stage 5: Dashboard (non-fatal — detection results are already saved)
    logger.info("=" * 60)
    logger.info("STAGE 5: Building dashboard")
    logger.info("=" * 60)
    try:
        dashboard_path = generate_dashboard(
            results, alerts,
            sensitivity=sensitivity,
            lookback_days=lookback_days,
            validation_failures=validation_failures,
        )
        summary["dashboard_path"] = dashboard_path
    except Exception as exc:
        logger.exception("Dashboard generation failed (non-fatal): %s", exc)
        summary["dashboard_path"] = None
        summary["dashboard_error"] = str(exc)

    logger.info("=" * 60)
    logger.info("DONE  |  %d tickers  |  %d anomalies  |  %d signals  |  %s",
                summary["tickers_analyzed"], summary["anomalies_detected"],
                summary["total_signals"], summary.get("dashboard_path", "N/A"))
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
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip ticker validation (faster, for CI)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    try:
        summary = run(tickers=tickers, sensitivity=args.sensitivity,
                      lookback_days=args.lookback, skip_validation=args.skip_validation)
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
