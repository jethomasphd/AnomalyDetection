"""Main pipeline — orchestrates the full detection workflow.

Usage:
    python -m anomaly_detection.pipeline [options]

Operating model (v2, causal regime):

  * Detectors are causal: the verdict for bar t uses only bars <= t, so the
    same bar gets the same verdict no matter when it is scored. The first
    run over history is therefore a true walk-forward simulation
    (provenance='backfill', detected_at = bar date); subsequent runs score
    only bars beyond each ticker's watermark (provenance='live',
    detected_at = run date).

  * Durability: the SQLite store is a local cache. The committed JSONL
    ledger under data/ledger/ is the source of truth — on a fresh checkout
    (every CI run) the store is rebuilt from the ledger, so watermarks and
    frozen verdicts genuinely survive between runs.

  * The backtest consumes the FULL signals ledger (never the display-capped
    alerts.json) and fills at the close of the first bar strictly after
    detected_at.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

from .adjustments import (
    compute_ticker_status,
    detect_price_basis_breaks,
    detect_stale_feeds,
)
from .alerts import (
    alerts_to_json,
    alerts_to_markdown,
    append_new_alerts,
    generate_alerts,
    load_previous_alerts,
)
from .backtest import compute_backtest
from .config import (
    DATA_DIR,
    DEFAULT_SENSITIVITY,
    DEFAULT_TICKERS,
    DOCS_DIR,
    HISTORY_DIR,
    MODEL_VERSION,
    SIGNAL_START_DATE,
)
from .data_fetch import compute_features, fetch_multiple
from .detection.engine import run_all
from .storage import (
    alerts_to_signal_rows,
    bootstrap_from_ledger,
    count_rows,
    export_ledger,
    get_bar_watermarks,
    get_frozen_bar_closes,
    get_signals_for_backtest,
    reset_storage,
    results_to_anomaly_rows,
    update_bar_watermarks,
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


def _filter_to_new_bars(results: pd.DataFrame, watermarks: dict[str, str]) -> pd.DataFrame:
    """Keep only rows whose (ticker, date) is strictly after the ticker's watermark.

    Tickers without a watermark (first-ever run) are kept in full.
    """
    if results.empty:
        return results
    dates = pd.to_datetime(results["Date"]).dt.strftime("%Y-%m-%d")
    tickers = results["Ticker"].astype(str)
    wm = tickers.map(lambda t: watermarks.get(t))
    keep = wm.isna() | (dates > wm)
    return results.loc[keep].copy()


def _compute_watermarks(results: pd.DataFrame) -> dict[str, str]:
    """Return {ticker: max_date_str} from a detection-results frame."""
    if results.empty:
        return {}
    dates = pd.to_datetime(results["Date"]).dt.strftime("%Y-%m-%d")
    return (
        pd.DataFrame({"ticker": results["Ticker"].astype(str), "date": dates})
        .groupby("ticker")["date"].max()
        .to_dict()
    )


def _write_run_history(summary: dict) -> None:
    """Append this run's summary to data/history/ and refresh the index."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    run_path = os.path.join(HISTORY_DIR, f"run_{summary['run_date']}.json")
    with open(run_path, "w") as f:
        json.dump(summary, f, indent=2)

    index = []
    for fname in sorted(os.listdir(HISTORY_DIR)):
        if fname.startswith("run_") and fname.endswith(".json"):
            try:
                with open(os.path.join(HISTORY_DIR, fname)) as f:
                    index.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    with open(os.path.join(HISTORY_DIR, "index.json"), "w") as f:
        json.dump(index, f, indent=2)


def run(
    tickers: list[str] | None = None,
    sensitivity: str = DEFAULT_SENSITIVITY,
    start_date: str = SIGNAL_START_DATE,
    skip_validation: bool = False,
    reset: bool = False,
) -> dict:
    """Execute the full anomaly detection pipeline.

    THE SIGNAL anchors on `start_date`. Tickers without a watermark are
    backfilled with a walk-forward simulation over their history; tickers
    with a watermark get live verdicts on new bars only. Once a bar is
    written its verdict is frozen — the ledger is an immutable audit trail
    and the backtest is reproducible across runs.

    `reset=True` wipes the durable store, ledger, and alerts.json first
    (use when switching detection regimes, e.g. v1 percentile -> v2 causal).
    """
    started_at = datetime.utcnow()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    if reset:
        logger.warning("Reset requested — wiping durable store, ledger, and alerts.json")
        reset_storage()
        alerts_json = os.path.join(DATA_DIR, "alerts.json")
        if os.path.exists(alerts_json):
            os.remove(alerts_json)

    # Stage 0a: Rebuild the SQLite cache from the committed ledger if needed.
    # This is what makes durability real on ephemeral CI runners.
    if bootstrap_from_ledger():
        logger.info("SQLite cache rebuilt from committed ledger (fresh checkout)")

    # Stage 0b: Ticker validation (optional, skipped in CI for speed)
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

    # Stage 1: Fetch (with retry + coverage report)
    logger.info("=" * 60)
    logger.info("STAGE 1: Fetching stock data from %s", start_date)
    logger.info("=" * 60)
    raw_df, fetch_report = fetch_multiple(
        tickers=effective_tickers, start_date=start_date, return_report=True
    )

    # Stage 2: Features
    logger.info("=" * 60)
    logger.info("STAGE 2: Computing features")
    logger.info("=" * 60)
    featured_df = compute_features(raw_df)
    featured_df.to_csv(os.path.join(DATA_DIR, "stock_data.csv"), index=False)

    # Stage 3: Detection (causal — scores for old bars never change)
    logger.info("=" * 60)
    logger.info("STAGE 3: Running anomaly detection (4 causal methods)")
    logger.info("=" * 60)
    results = run_all(featured_df, sensitivity=sensitivity)
    results.to_csv(os.path.join(DATA_DIR, "detection_results.csv"), index=False)

    # Stage 3a: Feed health + price-basis reconciliation (adjustments.py).
    # Both checks compare the FRESH fetch against the FROZEN record:
    #   * a flatlined series (identical trailing closes) means the upstream
    #     feed is stale — its new bars are kept out of the frozen record so
    #     a dead feed can never mint permanent verdicts;
    #   * a frozen close that no longer matches the current close for the
    #     same bar means a corporate action rescaled the fetched history —
    #     frozen dollar values must be basis-translated wherever they are
    #     compared against fresh prices (backtest targets, dashboard).
    frozen_reference = get_frozen_bar_closes()
    basis_breaks = detect_price_basis_breaks(results, frozen_reference)
    stale_feeds = detect_stale_feeds(results)

    # Stage 3b: Edge-only persistence with provenance.
    # Tickers WITHOUT a watermark are being seen for the first time: their
    # history is persisted as a walk-forward backfill (detected_at = bar
    # date, which causality makes honest). Tickers WITH a watermark get
    # live rows (detected_at = run date) for bars beyond the watermark.
    watermarks = get_bar_watermarks()
    new_bars = _filter_to_new_bars(results, watermarks)
    if stale_feeds:
        before = len(new_bars)
        new_bars = new_bars[~new_bars["Ticker"].astype(str).isin(stale_feeds)].copy()
        logger.warning(
            "Stale feeds %s: excluded %d new bars from the frozen record "
            "(they will be re-scored once the feed moves again)",
            sorted(stale_feeds), before - len(new_bars),
        )
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    known = new_bars["Ticker"].astype(str).isin(set(watermarks.keys()))
    live_bars = new_bars[known]
    backfill_bars = new_bars[~known]
    logger.info(
        "Edge persist: %d live bars (%d tickers) + %d backfill bars (%d tickers) "
        "of %d scored",
        len(live_bars), live_bars["Ticker"].nunique() if not live_bars.empty else 0,
        len(backfill_bars), backfill_bars["Ticker"].nunique() if not backfill_bars.empty else 0,
        len(results),
    )

    anomaly_rows = results_to_anomaly_rows(live_bars, detected_at=run_date, provenance="live")
    anomaly_rows += results_to_anomaly_rows(backfill_bars, provenance="backfill")
    upsert_anomalies(anomaly_rows)

    # Stage 4: Signals — generated only from new bars, then merged with the
    # frozen display history. The ledger receives every signal; alerts.json
    # is a capped view for the dashboard.
    logger.info("=" * 60)
    logger.info("STAGE 4: Generating trading signals (edge-only)")
    logger.info("=" * 60)
    new_alerts = []
    if not live_bars.empty:
        new_alerts += generate_alerts(live_bars, sensitivity=sensitivity, provenance="live")
    if not backfill_bars.empty:
        new_alerts += generate_alerts(backfill_bars, sensitivity=sensitivity, provenance="backfill")

    # Recomputed views: current-price context per ticker and proof the run
    # actually scored bars — written next to (never into) the frozen rows.
    ticker_status = compute_ticker_status(results, basis_breaks, stale_feeds)
    latest_bar_date = pd.to_datetime(results["Date"]).max().strftime("%Y-%m-%d")
    run_info = {
        "run_date": run_date,
        "new_bars_scored": len(new_bars),
        "latest_bar_date": latest_bar_date,
        "tickers_scored": int(results["Ticker"].nunique()),
        "new_signals": len(new_alerts),
    }

    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    previous_alerts = load_previous_alerts(alerts_path)
    alerts = append_new_alerts(new_alerts, previous_alerts)
    alerts_to_json(alerts, alerts_path, run_info=run_info, ticker_status=ticker_status)

    # Persist ONLY the new signals to the store (frozen once written).
    upsert_signals(alerts_to_signal_rows(new_alerts))

    # Advance watermarks, then export the ledger — the committed truth.
    # Stale-feed tickers keep their old watermark so their flatlined bars
    # are re-scored on the first run after the feed recovers.
    update_bar_watermarks({
        t: d for t, d in _compute_watermarks(results).items() if t not in stale_feeds
    })
    ledger_counts = export_ledger()
    store_counts = count_rows()
    logger.info("Store: %d anomaly rows, %d signal rows (ledger: %s)",
                store_counts["anomalies"], store_counts["signals"], ledger_counts)

    print("\n" + alerts_to_markdown([a for a in alerts if a.get("is_new")] or alerts[:10]))

    # Stage 5: Walk-forward backtest from the FULL signals ledger.
    logger.info("=" * 60)
    logger.info("STAGE 5: Walk-forward backtest (next-bar fills, costs, time stop)")
    logger.info("=" * 60)
    ledger_signals = get_signals_for_backtest()
    backtest = compute_backtest(results, ledger_signals)
    logger.info(
        "Backtest: %d trades (%d closed, %d open, %d pending) | total $%+.2f | "
        "backfill vs live: %s",
        backtest["n_trades"], backtest["n_closed"], backtest["n_open"],
        backtest["n_pending"], backtest["total_gain"],
        {k: v["n_trades"] for k, v in backtest.get("provenance_stats", {}).items()},
    )

    # Build summary / health report
    finished_at = datetime.utcnow()
    summary = {
        "run_date": run_date,
        "started_at": started_at.isoformat() + "Z",
        "finished_at": finished_at.isoformat() + "Z",
        "duration_seconds": round((finished_at - started_at).total_seconds(), 1),
        "tickers_analyzed": int(results["Ticker"].nunique()),
        "total_observations": len(results),
        "anomalies_detected": int(results["consensus_anomaly"].sum()),
        "new_bars_scored": len(new_bars),
        "new_signals": len(new_alerts),
        "actionable_signals": sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE")),
        "total_signals_view": len(alerts),
        "ledger_signal_rows": store_counts["signals"],
        "ledger_anomaly_rows": store_counts["anomalies"],
        "backtest_total_gain": backtest["total_gain"],
        "backtest_n_trades": backtest["n_trades"],
        "sensitivity": sensitivity,
        "start_date": start_date,
        "model_version": MODEL_VERSION,
        "fetch": fetch_report,
        "validation_failures": validation_failures,
        "latest_bar_date": latest_bar_date,
        "stale_feeds": stale_feeds,
        "price_basis_breaks": basis_breaks,
    }

    health = {
        "run_date": run_date,
        "status": "degraded" if (fetch_report["failed"] or stale_feeds) else "ok",
        "coverage_pct": fetch_report["coverage_pct"],
        "tickers_requested": fetch_report["requested"],
        "tickers_fetched": fetch_report["fetched"],
        "fetch_failures": fetch_report["failed"],
        "stale_feeds": stale_feeds,
        "price_basis_breaks": basis_breaks,
        "latest_bar_date": latest_bar_date,
        "new_bars_scored": len(new_bars),
        "duration_seconds": summary["duration_seconds"],
        "model_version": MODEL_VERSION,
    }
    with open(os.path.join(DATA_DIR, "run_health.json"), "w") as f:
        json.dump(health, f, indent=2)
    _write_run_history(summary)

    # Stage 6: Dashboard (non-fatal — detection results are already saved)
    logger.info("=" * 60)
    logger.info("STAGE 6: Building dashboard")
    logger.info("=" * 60)
    try:
        dashboard_path = generate_dashboard(
            results, alerts,
            backtest=backtest,
            sensitivity=sensitivity,
            start_date=start_date,
            validation_failures=validation_failures,
            health=health,
            run_info=run_info,
            ticker_status=ticker_status,
        )
        summary["dashboard_path"] = dashboard_path
    except Exception as exc:
        logger.exception("Dashboard generation failed (non-fatal): %s", exc)
        summary["dashboard_path"] = None
        summary["dashboard_error"] = str(exc)

    logger.info("=" * 60)
    logger.info("DONE  |  %d tickers  |  %d anomalies  |  %d new signals  |  %s",
                summary["tickers_analyzed"], summary["anomalies_detected"],
                summary["new_signals"], summary.get("dashboard_path", "N/A"))
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
  python -m anomaly_detection --sensitivity high
        """,
    )
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated tickers (default: built-in watchlist)")
    parser.add_argument("--sensitivity", type=str, choices=["low", "medium", "high"],
                        default=DEFAULT_SENSITIVITY)
    parser.add_argument("--start-date", type=str, default=SIGNAL_START_DATE,
                        help=f"Anchor date for history (default: {SIGNAL_START_DATE})")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip ticker validation (faster, for CI)")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe durable store, ledger, and alerts.json before running "
                             "(use when switching detection regimes)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    try:
        summary = run(tickers=tickers, sensitivity=args.sensitivity,
                      start_date=args.start_date, skip_validation=args.skip_validation,
                      reset=args.reset)
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
