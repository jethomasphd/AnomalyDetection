"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import (
    CATEGORY_LABELS,
    DOCS_DIR,
    TICKER_NAMES,
    TICKER_REGISTRY,
    TICKER_SECTORS,
    ticker_display,
    tickers_by_category,
)
from .charts import (
    backtest_equity_chart,
    compute_attention_queue,
    compute_backtest,
    method_ensemble_chart,
    method_ewma_chart,
    method_fourier_chart,
    method_mp_chart,
    scoreboard_chart,
    ticker_chart,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _estimate_market_caps(tickers: list[str]) -> dict[str, float | None]:
    """Try to get market cap for each ticker (best-effort, cached)."""
    caps = {}
    try:
        import yfinance as yf
        for t in tickers:
            try:
                info = yf.Ticker(t).info
                caps[t] = info.get("marketCap")
            except Exception:
                caps[t] = None
    except ImportError:
        pass
    return caps


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    lookback_days: int = 365,
    output_path: str | None = None,
    validation_failures: list[dict] | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk."""
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tickers = sorted(results["Ticker"].unique())
    signal_tickers = {a["ticker"] for a in alerts} if alerts else set()

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

    # Backtest
    backtest = compute_backtest(results, alerts)
    backtest_chart_json = backtest_equity_chart(backtest)

    # Market caps for ticker ordering
    market_caps = _estimate_market_caps(tickers)

    # Top 12 by market cap (for button display)
    tickers_with_cap = [(t, market_caps.get(t) or 0) for t in tickers]
    tickers_with_cap.sort(key=lambda x: x[1], reverse=True)
    top12_tickers = [t for t, _ in tickers_with_cap[:12]]
    remaining_tickers = [t for t, _ in tickers_with_cap[12:]]

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_actionable = sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE"))
    n_new_signals = sum(1 for a in alerts if a.get("is_new", False))

    # Build ticker display info
    ticker_info = []
    for t in tickers:
        ticker_info.append({
            "ticker": t,
            "display": ticker_display(t),
            "name": TICKER_NAMES.get(t, t),
            "sector": TICKER_SECTORS.get(t, ""),
            "has_signal": t in signal_tickers,
            "market_cap": market_caps.get(t),
            "is_fund": TICKER_REGISTRY.get(t, {}).get("is_fund", False),
            "category": TICKER_REGISTRY.get(t, {}).get("category", ""),
        })

    # Category grouping for display
    cat_groups = tickers_by_category()

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_tickers=len(tickers),
        n_anomalies=n_anomalies,
        n_actionable=n_actionable,
        n_new_signals=n_new_signals,
        lookback_days=lookback_days,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        alerts=alerts,
        tickers=tickers,
        ticker_info=ticker_info,
        signal_tickers=signal_tickers,
        ticker_charts_json=json.dumps(ticker_charts),
        method_charts_json=json.dumps(method_charts),
        scoreboard_json=scoreboard_json,
        attention_queue=attention_queue,
        attention_queue_json=json.dumps(attention_queue),
        backtest=backtest,
        backtest_chart_json=backtest_chart_json,
        top12_tickers=top12_tickers,
        remaining_tickers=remaining_tickers,
        category_labels=CATEGORY_LABELS,
        category_groups=cat_groups,
        validation_failures=validation_failures or [],
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
