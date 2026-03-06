"""Main pipeline — orchestrates the full Cool Runnings spam rate detection workflow.

"I see pride! I see power! I see a bad-ass mother who don't take no crap off of nobody!"

Usage:
    python -m spam_detection [options]

This pipeline runs five stages:
  1. Load Postmaster data (simplified ETL — one file, no merging)
  2. Compute features
  3. Run four detection methods (Feel the Rhythm / Rhyme / Get on Up / Bobsled Time)
  4. Generate alerts (incremental — merge with previous run)
  5. Build the Cool Runnings dashboard
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

from .alerts import alerts_to_json, alerts_to_markdown, generate_alerts, load_previous_alerts, merge_alerts
from .config import DATA_DIR, DEFAULT_DATA_CSV_PATH, DEFAULT_DATA_PATH, DEFAULT_SENSITIVITY, DOCS_DIR
from .data_load import compute_features, load_data
from .detection.engine import run_all
from .visualization.dashboard import generate_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(
    data_path: str = DEFAULT_DATA_PATH,
    data_csv_path: str = DEFAULT_DATA_CSV_PATH,
    domains: list[str] | None = None,
    sensitivity: str = DEFAULT_SENSITIVITY,
) -> dict:
    """Execute the full anomaly detection pipeline.

    "Feel the rhythm, feel the rhyme, get on up, it's bobsled time!"
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Stage 1: Load
    logger.info("=" * 60)
    logger.info("STAGE 1: Loading Postmaster data")
    logger.info("  One file in, clean data out. No merging, no fuss.")
    logger.info("=" * 60)
    raw_df = load_data(data_path=data_path, domains=domains)

    # Stage 2: Features
    logger.info("=" * 60)
    logger.info("STAGE 2: Computing features")
    logger.info("=" * 60)
    featured_df = compute_features(raw_df)
    featured_df.to_csv(os.path.join(DATA_DIR, "spam_data.csv"), index=False)

    # Stage 3: Detection
    logger.info("=" * 60)
    logger.info("STAGE 3: Running anomaly detection (4 methods)")
    logger.info("  Feel the Rhythm / Feel the Rhyme / Get on Up / Bobsled Time")
    logger.info("=" * 60)
    results = run_all(featured_df, sensitivity=sensitivity)
    results.to_csv(os.path.join(DATA_DIR, "detection_results.csv"), index=False)

    # Stage 4: Signals (incremental — merge with previous run)
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating Cool Runnings alerts (incremental)")
    logger.info("=" * 60)
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    previous_alerts = load_previous_alerts(alerts_path)
    new_alerts = generate_alerts(results, previous_alerts=previous_alerts)
    alerts = merge_alerts(new_alerts, previous_alerts)
    alerts_to_json(alerts, alerts_path)
    print("\n" + alerts_to_markdown(alerts))

    # Date range from data
    date_min = results["Date"].min()
    date_max = results["Date"].max()
    date_range_days = (date_max - date_min).days if hasattr(date_max - date_min, "days") else 0

    # Build summary
    summary = {
        "run_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "system": "Cool Runnings Spam Rate Monitor",
        "domains_analyzed": int(results["Domain"].nunique()),
        "total_observations": len(results),
        "anomalies_detected": int(results["consensus_anomaly"].sum()),
        "actionable_signals": sum(1 for a in alerts if a["signal"] != "WATCH"),
        "total_signals": len(alerts),
        "sensitivity": sensitivity,
        "date_range": f"{date_min.strftime('%Y-%m-%d')} to {date_max.strftime('%Y-%m-%d')}",
        "date_range_days": date_range_days,
    }

    # Stage 5: Dashboard
    logger.info("=" * 60)
    logger.info("STAGE 5: Building Cool Runnings dashboard")
    logger.info("=" * 60)
    dashboard_path = generate_dashboard(
        results, alerts,
        sensitivity=sensitivity,
        data_csv_path=data_csv_path,
    )

    summary["dashboard_path"] = dashboard_path

    logger.info("=" * 60)
    logger.info(
        "DONE  |  %d domains  |  %d anomalies  |  %d signals  |  %s",
        summary["domains_analyzed"],
        summary["anomalies_detected"],
        summary["total_signals"],
        dashboard_path,
    )
    logger.info("  Feel the rhythm, feel the rhyme, get on up, it's bobsled time!")
    logger.info("=" * 60)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Cool Runnings Google Spam Rate Anomaly Detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
"Feel the rhythm, feel the rhyme, get on up, it's bobsled time!"

Examples:
  python -m spam_detection                                     # defaults (Postmaster.csv)
  python -m spam_detection --data path/to/postmaster.csv       # custom data file
  python -m spam_detection --domains "yayjobs.net,aptena.com"  # specific domains
  python -m spam_detection --sensitivity high                  # sensitive detection
        """,
    )
    parser.add_argument(
        "--data", type=str, default=DEFAULT_DATA_PATH,
        help="Path to Postmaster CSV data file (default: Postmaster.csv)",
    )
    parser.add_argument(
        "--data-csv", type=str, default=DEFAULT_DATA_CSV_PATH,
        help="Path to data.csv for country distribution (default: data.csv)",
    )
    parser.add_argument(
        "--domains", type=str, default="",
        help="Comma-separated domains to analyze (default: auto-discover from data)",
    )
    parser.add_argument(
        "--sensitivity", type=str, choices=["low", "medium", "high"],
        default=DEFAULT_SENSITIVITY,
        help="Detection sensitivity: low (fewer alerts), medium (balanced), high (more alerts)",
    )
    args = parser.parse_args()

    domains = [d.strip() for d in args.domains.split(",") if d.strip()] or None

    try:
        summary = run(data_path=args.data, data_csv_path=args.data_csv, domains=domains, sensitivity=args.sensitivity)
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
