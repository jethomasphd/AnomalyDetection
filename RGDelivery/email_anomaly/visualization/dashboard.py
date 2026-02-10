"""Dashboard generator — renders the Jinja2 template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import DOCS_DIR
from .charts import (
    domain_chart,
    method_ensemble_chart,
    method_ewma_chart,
    method_fourier_chart,
    method_mp_chart,
    scoreboard_chart,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    output_path: str | None = None,
) -> str:
    """Generate the full HTML dashboard and write it to disk."""
    output_path = output_path or os.path.join(DOCS_DIR, "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    domains = sorted(results["Domain"].unique())
    signal_domains = {a["domain"] for a in alerts} if alerts else set()

    # Date range
    date_min = results["Date"].min()
    date_max = results["Date"].max()
    date_range_days = (date_max - date_min).days if hasattr(date_max - date_min, "days") else 0

    # Per-domain main charts + method detail charts
    domain_charts = {}
    method_charts = {}
    for domain in domains:
        df_d = results[results["Domain"] == domain]
        domain_charts[domain] = json.loads(domain_chart(df_d, domain, signals=alerts))
        method_charts[domain] = {
            "fourier": json.loads(method_fourier_chart(df_d, domain)),
            "matrix_profile": json.loads(method_mp_chart(df_d, domain)),
            "ensemble": json.loads(method_ensemble_chart(df_d, domain)),
            "ewma": json.loads(method_ewma_chart(df_d, domain)),
        }

    # Summary charts
    scoreboard_json = scoreboard_chart(results)

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_actionable = sum(1 for a in alerts if a["signal"] != "WATCH")

    # Build domain display info for template
    domain_info = []
    for d in domains:
        domain_info.append({
            "domain": d,
            "display": d if len(d) <= 30 else d[:27] + "...",
            "has_signal": d in signal_domains,
        })

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_domains=len(domains),
        n_anomalies=n_anomalies,
        n_actionable=n_actionable,
        date_range_days=date_range_days,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        alerts=alerts,
        domains=domains,
        domain_info=domain_info,
        signal_domains=signal_domains,
        domain_charts_json=json.dumps(domain_charts),
        method_charts_json=json.dumps(method_charts),
        scoreboard_json=scoreboard_json,
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
