"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import DOCS_DIR
from .charts import alert_distribution_chart, summary_heatmap, ticker_chart

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    lookback_days: int = 365,
    output_path: str | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk.

    Returns the path to the generated HTML file.
    """
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tickers = sorted(results["Ticker"].unique())
    anomaly_tickers = set()
    if alerts:
        anomaly_tickers = {a["ticker"] for a in alerts}

    # Generate per-ticker charts
    ticker_charts = {}
    for ticker in tickers:
        df_t = results[results["Ticker"] == ticker]
        chart_json = ticker_chart(df_t, ticker)
        ticker_charts[ticker] = json.loads(chart_json)

    # Generate summary charts
    heatmap_json = summary_heatmap(results)
    distribution_json = alert_distribution_chart(alerts)

    # Count stats
    n_anomalies = results["consensus_anomaly"].sum() if "consensus_anomaly" in results.columns else 0
    n_critical = sum(1 for a in alerts if a["severity"] == "CRITICAL")

    # Render template
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_tickers=len(tickers),
        n_anomalies=int(n_anomalies),
        n_critical=n_critical,
        lookback_days=lookback_days,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        alerts=alerts,
        tickers=tickers,
        anomaly_tickers=anomaly_tickers,
        ticker_charts_json=json.dumps(ticker_charts),
        heatmap_json=heatmap_json,
        distribution_json=distribution_json,
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
