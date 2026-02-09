"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import DOCS_DIR
from .charts import history_chart, scoreboard_chart, ticker_chart

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    lookback_days: int = 365,
    history_data: list[dict] | None = None,
    output_path: str | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk."""
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tickers = sorted(results["Ticker"].unique())
    anomaly_tickers = {a["ticker"] for a in alerts} if alerts else set()
    history_data = history_data or []

    # Per-ticker charts
    ticker_charts = {}
    for ticker in tickers:
        df_t = results[results["Ticker"] == ticker]
        ticker_charts[ticker] = json.loads(ticker_chart(df_t, ticker))

    # Summary charts
    scoreboard_json = scoreboard_chart(results)
    history_json = history_chart(history_data) if history_data else "{}"

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_high = sum(1 for a in alerts if a["severity"] in ("CRITICAL", "HIGH"))

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_tickers=len(tickers),
        n_anomalies=n_anomalies,
        n_high=n_high,
        n_runs=len(history_data),
        lookback_days=lookback_days,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        alerts=alerts,
        tickers=tickers,
        anomaly_tickers=anomaly_tickers,
        has_history=len(history_data) > 1,
        ticker_charts_json=json.dumps(ticker_charts),
        scoreboard_json=scoreboard_json,
        history_json=history_json,
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
