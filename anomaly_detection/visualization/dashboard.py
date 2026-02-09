"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import DOCS_DIR, TICKER_NAMES, TICKER_SECTORS, ticker_display
from .charts import (
    method_ensemble_chart,
    method_ewma_chart,
    method_fourier_chart,
    method_mp_chart,
    scoreboard_chart,
    ticker_chart,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    lookback_days: int = 365,
    output_path: str | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk."""
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tickers = sorted(results["Ticker"].unique())
    signal_tickers = {a["ticker"] for a in alerts} if alerts else set()

    # Per-ticker main charts (pass signals for color-coded markers) + method detail charts
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

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_actionable = sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE"))

    # Build ticker display info for template
    ticker_info = []
    for t in tickers:
        ticker_info.append({
            "ticker": t,
            "display": ticker_display(t),
            "name": TICKER_NAMES.get(t, t),
            "sector": TICKER_SECTORS.get(t, ""),
            "has_signal": t in signal_tickers,
        })

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_tickers=len(tickers),
        n_anomalies=n_anomalies,
        n_actionable=n_actionable,
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
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
