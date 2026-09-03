"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import date, datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..adjustments import bar_basis_factor
from ..config import (
    BACKTEST_BASELINE_TICKER,
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    BACKTEST_UNIT_DOLLARS,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    DOCS_DIR,
    MODEL_VERSION,
    PORTFOLIO_CAPITAL,
    PRICE_BASIS_TOLERANCE,
    SENSITIVITY_PRESETS,
    TICKER_NAMES,
    TICKER_REGISTRY,
    TICKER_SECTORS,
    TRADE_MIN_ABS_DEVIATION_PCT,
    ticker_display,
    tickers_by_category,
)
from ..backtest import compute_backtest
from ..storage import get_frozen_bar_closes, get_signals_for_backtest
from .charts import (
    attention_heatmap_chart,
    backtest_equity_chart,
    compute_attention_queue,
    method_ensemble_chart,
    method_ewma_chart,
    method_fourier_chart,
    method_mp_chart,
    scoreboard_chart,
    ticker_chart,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


# Pinned buttons for the deep-dive section (always visible)
PINNED_DEEP_DIVE = [
    "SPY", "QQQ", "VOO",
    "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "TSLA", "META",
    "JPM", "UNH", "WMT", "COST", "HD",
    "DVRUX", "QGRPX", "BNUEX",
]


def _annotate_signal_staleness(alerts: list[dict], stale_after_days: int = 14) -> None:
    """Add `days_old` and `is_stale` to each alert, in-place.

    Staleness is measured from the signal's bar `date` to today. The
    detected_at is shown on the card as the audit anchor, but staleness is
    about how long the trading call has been sitting on the board — an open
    BUY from 40 days ago deserves a visual warning.
    """
    today = date.today()
    for a in alerts or []:
        raw = a.get("date")
        if not raw:
            a["days_old"] = None
            a["is_stale"] = False
            continue
        try:
            d = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            a["days_old"] = None
            a["is_stale"] = False
            continue
        a["days_old"] = (today - d).days
        a["is_stale"] = a["days_old"] > stale_after_days


def _annotate_price_basis(
    alerts: list[dict],
    results: pd.DataFrame,
    ticker_status: dict | None = None,
    tolerance: float = PRICE_BASIS_TOLERANCE,
) -> None:
    """Add current-price context to each alert, in-place.

    A signal row shows its close FROZEN at detection time; without context
    a reader mistakes it for the model's current price (and after a split
    it doesn't even match the current chart). Each alert gains:

      current_price / current_date — the ticker's latest fetched close.
      basis_factor  — frozen close ÷ current close for the SAME bar; ≈1
                      normally, ≈4 after a 4:1 split rescaled the history.
      basis_changed — True when the factor breaches `tolerance`.
      pct_since     — % move from the (basis-translated) signal close to
                      the current price; comparable across splits.
    """
    if not alerts or results is None or results.empty:
        return
    current: dict[str, dict[str, float]] = {}
    latest: dict[str, tuple[str, float]] = {}
    for ticker, grp in results.groupby("Ticker"):
        g = grp.sort_values("Date")
        dates = pd.to_datetime(g["Date"]).dt.strftime("%Y-%m-%d")
        closes = g["Close"].astype(float)
        current[str(ticker)] = dict(zip(dates, closes))
        latest[str(ticker)] = (dates.iloc[-1], float(closes.iloc[-1]))

    for a in alerts:
        a.setdefault("current_price", None)
        a.setdefault("basis_factor", None)
        a.setdefault("basis_changed", False)
        a.setdefault("pct_since", None)
        t = a.get("ticker")
        if t not in latest:
            continue
        last_date, last_close = latest[t]
        a["current_price"] = round(last_close, 2)
        a["current_date"] = last_date
        factor = bar_basis_factor(a.get("close"), current[t].get(a.get("date")))
        if factor is None:
            # Signal bar absent from the current fetch (feed revised the
            # date, or the window slid past it). Fall back to the ticker's
            # known basis break so a frozen pre-split price is never shown
            # next to a post-split "now" price without explanation.
            basis = ((ticker_status or {}).get(t) or {}).get("price_basis")
            factor = basis.get("factor") if basis else None
        if factor is None:
            continue
        a["basis_factor"] = round(factor, 4)
        a["basis_changed"] = abs(factor - 1.0) > tolerance
        signal_close_now = a["close"] / factor  # frozen close in today's basis
        if signal_close_now > 0:
            a["pct_since"] = round((last_close / signal_close_now - 1) * 100, 1)


def explainer_context(backtest: dict | None, sensitivity: str = "medium") -> dict:
    """Facts behind the dashboard's "What am I looking at?" panel.

    Everything the panel states — the sigma threshold, the materiality gate,
    the slice size, the time stop, and the record so far — is read from the
    protocol parameters and the walk-forward backtest, never typed into the
    template, so the copy can never drift from what the model actually does.
    """
    bt = backtest or {}
    preset = SENSITIVITY_PRESETS.get(str(sensitivity).lower(), SENSITIVITY_PRESETS["medium"])
    capital = float(bt.get("initial_capital") or PORTFOLIO_CAPITAL)
    unit = float(bt.get("unit") or BACKTEST_UNIT_DOLLARS)
    stats = bt.get("stats") or {}
    prov = (bt.get("provenance_stats") or {}).get("live") or {}
    n_trades = int(bt.get("n_trades") or 0)
    n_winning = int(bt.get("n_winning") or 0)
    final_value = bt.get("final_value")
    benchmark_pct = stats.get("benchmark_return_pct")
    return {
        "z_threshold": preset["z_threshold"],
        "materiality_pct": TRADE_MIN_ABS_DEVIATION_PCT,
        "max_hold": int(bt.get("max_hold_days") or BACKTEST_MAX_HOLD_TRADING_DAYS),
        "baseline": bt.get("baseline_ticker") or BACKTEST_BASELINE_TICKER,
        "unit_pct": int(round(unit / capital * 100)) if capital else 0,
        "capital": capital,
        # The record so far — only shown once the backtest has something to say.
        "has_record": bool(bt.get("signal_ledger")) and final_value is not None and benchmark_pct is not None,
        "final_value": final_value,
        "benchmark_value": (capital * (1 + benchmark_pct / 100.0)) if benchmark_pct is not None else None,
        "strategy_pct": stats.get("strategy_return_pct"),
        "benchmark_pct": benchmark_pct,
        "excess_gain": stats.get("excess_gain"),
        "n_trades": n_trades,
        "win_rate_pct": (n_winning / n_trades * 100.0) if n_trades else None,
        "live_n": int(prov.get("n_trades") or 0),
        "live_pnl": float(prov.get("realized_gain") or 0) + float(prov.get("unrealized_gain") or 0),
        "start_date": bt.get("start_date"),
        "end_date": bt.get("end_date"),
    }


def _deep_dive_buttons(tickers: list[str]) -> tuple[list[str], list[str]]:
    """Return (pinned_buttons, dropdown_remaining) for the deep-dive section.

    Pinned buttons are the PINNED_DEEP_DIVE tickers (in fixed order).
    Dropdown contains all remaining tickers sorted alphabetically.
    """
    pinned = [t for t in PINNED_DEEP_DIVE if t in tickers]
    remaining = sorted([t for t in tickers if t not in pinned])
    return pinned, remaining


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    backtest: dict | None = None,
    sensitivity: str = "medium",
    start_date: str = "2024-11-01",
    output_path: str | None = None,
    validation_failures: list[dict] | None = None,
    health: dict | None = None,
    run_info: dict | None = None,
    ticker_status: dict | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk.

    `backtest` is the walk-forward result from anomaly_detection.backtest;
    if omitted it is computed here from the full signals ledger.
    """
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if backtest is None:
        backtest = compute_backtest(results, get_signals_for_backtest(),
                                    frozen_closes=get_frozen_bar_closes())

    tickers = sorted(results["Ticker"].unique())
    signal_tickers = {a["ticker"] for a in alerts} if alerts else set()

    _annotate_signal_staleness(alerts, stale_after_days=14)
    _annotate_price_basis(alerts, results, ticker_status=ticker_status)

    # Per-ticker main charts + method detail charts
    ticker_charts = {}
    method_charts = {}
    for ticker in tickers:
        df_t = results[results["Ticker"] == ticker]
        ticker_charts[ticker] = json.loads(ticker_chart(df_t, ticker, signals=alerts))
        method_charts[ticker] = {
            "fourier": json.loads(method_fourier_chart(df_t, ticker)),
            "matrix_profile": json.loads(method_mp_chart(df_t, ticker)),
            "ensemble": json.loads(method_ensemble_chart(df_t, ticker)),
            "ewma": json.loads(method_ewma_chart(df_t, ticker)),
        }

    # Summary charts
    scoreboard_json = scoreboard_chart(results)

    # Attention Queue
    attention_queue = compute_attention_queue(results, alerts)

    # Attention heatmap (with signal info on hover)
    heatmap_json = attention_heatmap_chart(results, alerts=alerts)

    # Backtest equity chart (walk-forward result computed from the ledger)
    backtest_chart_json = backtest_equity_chart(backtest)

    # Deep-dive buttons: pinned set + alphabetical dropdown
    pinned_tickers, remaining_tickers = _deep_dive_buttons(tickers)

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_actionable = sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE"))
    n_new_signals = sum(1 for a in alerts if a.get("is_new", False))
    new_alerts = [a for a in alerts if a.get("is_new", False)]

    # Build ticker display info
    ticker_info = []
    for t in tickers:
        ticker_info.append({
            "ticker": t,
            "display": ticker_display(t),
            "name": TICKER_NAMES.get(t, t),
            "sector": TICKER_SECTORS.get(t, ""),
            "has_signal": t in signal_tickers,
            "is_fund": TICKER_REGISTRY.get(t, {}).get("is_fund", False),
            "category": TICKER_REGISTRY.get(t, {}).get("category", ""),
        })

    cat_groups = tickers_by_category()

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_tickers=len(tickers),
        n_anomalies=n_anomalies,
        n_actionable=n_actionable,
        n_new_signals=n_new_signals,
        start_date=start_date,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        model_version=MODEL_VERSION,
        run_date=date.today().strftime("%Y-%m-%d"),
        alerts=alerts,
        new_alerts=new_alerts,
        tickers=tickers,
        ticker_info=ticker_info,
        signal_tickers=signal_tickers,
        ticker_charts_json=json.dumps(ticker_charts),
        method_charts_json=json.dumps(method_charts),
        scoreboard_json=scoreboard_json,
        attention_queue=attention_queue,
        attention_queue_json=json.dumps(attention_queue),
        heatmap_json=heatmap_json,
        backtest=backtest,
        backtest_chart_json=backtest_chart_json,
        explainer=explainer_context(backtest, sensitivity),
        pinned_tickers=pinned_tickers,
        remaining_tickers=remaining_tickers,
        category_labels=CATEGORY_LABELS,
        category_groups=cat_groups,
        validation_failures=validation_failures or [],
        health=health or {},
        run_info=run_info or {},
        ticker_status=ticker_status or {},
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
