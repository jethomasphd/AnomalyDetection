"""Capacity study: re-run the walk-forward backtest at several capital levels.

The production backtest runs a $100,000 book with $10,000 slices. Before
funding a larger book, run this after a pipeline execution (it needs the
regenerated detection results in data/detection_results.csv) to see how
many of the skipped BUY signals a larger book would have funded, and what
the resulting curve looks like under two sizing policies:

  * proportional — the slice stays 10% of capital (same 10-slice book the
    split-half study validated; the curve scales linearly by construction),
  * fixed-slice  — the slice stays at $10,000 and the extra capital funds
    signals the small book had to skip (more concurrent single-name
    exposure; this is the untested configuration the prospectus flags).

    python -m anomaly_detection            # produces data/detection_results.csv
    python reports/prospectus/capacity_study.py --capital 250000 500000 1000000
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from anomaly_detection.backtest import compute_backtest  # noqa: E402
from anomaly_detection.config import BACKTEST_UNIT_DOLLARS, DATA_DIR, PORTFOLIO_CAPITAL  # noqa: E402
from anomaly_detection.storage import (  # noqa: E402
    bootstrap_from_ledger,
    get_frozen_bar_closes,
    get_signals_for_backtest,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capital", nargs="+", type=float, default=[250_000, 500_000, 1_000_000])
    ap.add_argument("--results", default=os.path.join(DATA_DIR, "detection_results.csv"))
    args = ap.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"{args.results} not found — run the pipeline first (python -m anomaly_detection)")
    results = pd.read_csv(args.results, parse_dates=["Date"])
    bootstrap_from_ledger()
    signals = get_signals_for_backtest()
    frozen = get_frozen_bar_closes()

    rows = []
    variants = [("production", PORTFOLIO_CAPITAL, BACKTEST_UNIT_DOLLARS)]
    for cap in args.capital:
        variants.append((f"proportional ${cap:,.0f}", cap, cap * BACKTEST_UNIT_DOLLARS / PORTFOLIO_CAPITAL))
        variants.append((f"fixed-slice ${cap:,.0f}", cap, BACKTEST_UNIT_DOLLARS))
    for label, cap, unit in variants:
        bt = compute_backtest(results, signals, capital=cap, unit=unit, frozen_closes=frozen)
        s = bt["stats"]
        rows.append({
            "variant": label, "capital": cap, "slice": unit,
            "trades": bt["n_trades"], "skipped": bt["n_skipped_no_capital"],
            "strategy_%": s["strategy_return_pct"], "baseline_%": s["benchmark_return_pct"],
            "excess_pp": s["excess_return_pct"], "sharpe": s["sharpe"],
            "max_dd_%": s["max_drawdown_pct"], "win_rate_%": s["win_rate"], "profit_factor": s["profit_factor"],
        })
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capacity_study.csv")
    df.to_csv(out, index=False)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
