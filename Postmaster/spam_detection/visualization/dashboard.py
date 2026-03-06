"""Dashboard generator — renders the Cool Runnings template with chart data."""

import json
import logging
import os
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..config import DEFAULT_DATA_CSV_PATH, DOCS_DIR, GOOGLE_THRESHOLDS
from ..data_load import load_country_distribution
from .charts import (
    country_pie_chart,
    domain_chart,
    method_ensemble_chart,
    method_ewma_chart,
    method_fourier_chart,
    method_mp_chart,
    overall_spam_rate_chart,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Google's compliance threshold (0.3%)
COMPLIANCE_THRESHOLD = GOOGLE_THRESHOLDS["monitor"]


def generate_dashboard(
    results: pd.DataFrame,
    alerts: list[dict],
    sensitivity: str = "medium",
    output_path: str | None = None,
    data_csv_path: str = DEFAULT_DATA_CSV_PATH,
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

    # Overall spam rate chart (6-month avg with linear fit)
    overall_chart_json = overall_spam_rate_chart(results)

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

    # Compliance stats: domains over 0.3% threshold
    n_over_threshold = sum(1 for r in latest_spam.values() if r > COMPLIANCE_THRESHOLD)
    pct_over_threshold = (n_over_threshold / len(domains) * 100) if domains else 0
    n_compliant = len(domains) - n_over_threshold
    pct_compliant = 100 - pct_over_threshold

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

    # --- Top 12 Offenders (highest spam rate) and Bottom 12 Performers (lowest spam rate) ---
    offenders = domain_ranking[:12]  # already sorted highest first
    performers = domain_ranking[-12:][::-1]  # lowest spam rate, reversed so lowest first

    # --- Country distribution pie charts ---
    offender_domains = [d["domain"] for d in offenders]
    performer_domains = [d["domain"] for d in performers]

    offender_country_data = load_country_distribution(offender_domains, data_csv_path)
    performer_country_data = load_country_distribution(performer_domains, data_csv_path)

    offender_pie_json = country_pie_chart(
        offender_country_data,
        "Proportion of Total Sends by Country<br>Among Domains with Significantly Higher Google Spam Rate",
        "#D50000",
    )
    performer_pie_json = country_pie_chart(
        performer_country_data,
        "Proportion of Total Sends by Country<br>Among Domains with Significantly Lower Google Spam Rate",
        "#009B3A",
    )

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
        overall_chart_json=overall_chart_json,
        # Compliance stats
        n_over_threshold=n_over_threshold,
        pct_over_threshold=f"{pct_over_threshold:.0f}",
        n_compliant=n_compliant,
        pct_compliant=f"{pct_compliant:.0f}",
        compliance_threshold_pct=f"{COMPLIANCE_THRESHOLD * 100:.1f}",
        # Offenders / Performers
        offenders=offenders,
        performers=performers,
        offender_pie_json=offender_pie_json,
        performer_pie_json=performer_pie_json,
    )

    with open(output_path, "w") as f:
        f.write(html)

    logger.info("Dashboard written to %s", output_path)
    return output_path
