"""Dashboard generator — renders the Cool Runnings template with chart data."""

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
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    output_path: str | None = None,
) -> str:
    """Generate the full Cool Runnings HTML dashboard and write it to disk."""
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

    # Stats
    n_anomalies = int(results["consensus_anomaly"].sum()) if "consensus_anomaly" in results.columns else 0
    n_actionable = sum(1 for a in alerts if a["signal"] != "WATCH")
    n_new_signals = sum(1 for a in alerts if a.get("is_new", False))

    # Count by severity
    n_urgent_critical = sum(1 for a in alerts if a["signal"] in ("URGENT", "CRITICAL"))

    # Build domain info with latest spam rate for sorting/display
    latest_per_domain = results.sort_values("Date").groupby("Domain").tail(1)
    latest_spam = dict(zip(latest_per_domain["Domain"], latest_per_domain["SpamRate"]))
    latest_reputation = dict(zip(
        latest_per_domain["Domain"],
        latest_per_domain["DomainReputation"] if "DomainReputation" in latest_per_domain.columns else ["N/A"] * len(latest_per_domain),
    ))

    # Build ranking data: domains sorted by recent spam rate (highest first)
    domain_ranking = []
    for d in domains:
        spam_rate = latest_spam.get(d, 0)
        domain_ranking.append({
            "domain": d,
            "display": d if len(d) <= 35 else d[:32] + "...",
            "spam_rate": spam_rate,
            "spam_rate_pct": f"{spam_rate * 100:.2f}%",
            "reputation": latest_reputation.get(d, "N/A"),
            "has_signal": d in signal_domains,
        })
    domain_ranking.sort(key=lambda x: x["spam_rate"], reverse=True)

    # Build domain_info: top 10 by spam rate as buttons, rest in dropdown (alphabetical)
    top_domains = domain_ranking[:10]
    rest_domains = sorted(domain_ranking[10:], key=lambda x: x["domain"])
    domain_info = top_domains + rest_domains

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template("dashboard.html")

    html = template.render(
        n_domains=len(domains),
        n_anomalies=n_anomalies,
        n_actionable=n_actionable,
        n_new_signals=n_new_signals,
        n_urgent_critical=n_urgent_critical,
        date_range_days=date_range_days,
        sensitivity=sensitivity.capitalize(),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        alerts=alerts,
        domains=domains,
        domain_info=domain_info,
        top_domains=top_domains,
        rest_domains=rest_domains,
        domain_ranking=domain_ranking,
        signal_domains=signal_domains,
        domain_charts_json=json.dumps(domain_charts),
        method_charts_json=json.dumps(method_charts),
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
