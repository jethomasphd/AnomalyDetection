"""Alert generation — human-readable summaries and structured JSON."""

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SEVERITY_MAP = {4: "CRITICAL", 3: "HIGH", 2: "MODERATE", 1: "LOW"}


def _describe_anomaly(row: pd.Series) -> str:
    """Generate a plain-English sentence explaining one anomaly."""
    parts = []

    # Lead with the most tangible signal: price vs. trend
    dev = row.get("deviation_pct", 0)
    trajectory = row.get("trajectory", "normal")

    if abs(dev) > 1:
        direction = "above" if dev > 0 else "below"
        lead = f"Price is {abs(dev):.1f}% {direction} its moving average"
        # Attach trajectory to the same sentence
        if trajectory == "breakout":
            lead += " with an extreme breakout from trend"
        elif trajectory == "accelerating":
            lead += " and momentum is building"
        elif trajectory == "decelerating":
            lead += " and momentum is fading"
        parts.append(lead)
    elif trajectory != "normal":
        labels = {"breakout": "Extreme breakout from trend", "accelerating": "Momentum is building", "decelerating": "Momentum is fading"}
        parts.append(labels.get(trajectory, trajectory))

    # Add color about what methods detected
    method_details = []
    if row.get("fourier_anomaly"):
        method_details.append("trading rhythm has changed structurally")
    if row.get("mp_anomaly"):
        method_details.append("recent price pattern has no historical match")
    if row.get("ensemble_anomaly"):
        method_details.append("multiple statistical tests confirm unusual behavior")

    if method_details:
        parts.append(". ".join(d.capitalize() for d in method_details))

    n = int(row.get("methods_flagged", 0))
    if n >= 2:
        parts.append(f"{n} of 4 detection methods flagged this")

    if not parts:
        parts.append("Elevated anomaly score across detection methods")

    return ". ".join(parts) + "."


def generate_alerts(results: pd.DataFrame, top_n: int = 50) -> list[dict]:
    """Generate structured alerts from detection results.

    Focuses on the most recent anomaly per ticker to avoid flooding
    the dashboard with repeats of the same event.
    """
    anomalies = results[results["consensus_anomaly"]].copy()
    if anomalies.empty:
        logger.info("No anomalies detected.")
        return []

    # Keep only the most recent anomaly per ticker, plus any high-severity historical ones
    latest_per_ticker = anomalies.sort_values("Date").groupby("Ticker").tail(1)
    high_severity = anomalies[anomalies["methods_flagged"] >= 3]
    combined = pd.concat([latest_per_ticker, high_severity]).drop_duplicates(subset=["Ticker", "Date"])
    combined = combined.sort_values("consensus_score", ascending=False)

    alerts = []
    for _, row in combined.head(top_n).iterrows():
        n_methods = int(row.get("methods_flagged", 0))
        severity = SEVERITY_MAP.get(n_methods, "LOW")
        alert = {
            "ticker": row["Ticker"],
            "date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"]),
            "close": round(float(row["Close"]), 2),
            "severity": severity,
            "methods_flagged": n_methods,
            "consensus_score": round(float(row["consensus_score"]), 4),
            "description": _describe_anomaly(row),
            "details": {
                "fourier_score": round(float(row.get("fourier_score", 0)), 4),
                "mp_score": round(float(row.get("mp_score", 0)), 4),
                "ensemble_score": round(float(row.get("ensemble_score", 0)), 4),
                "ewma_score": round(float(row.get("ewma_score", 0)), 4),
                "trajectory": row.get("trajectory", "normal"),
                "deviation_pct": round(float(row.get("deviation_pct", 0)), 2),
            },
        }
        alerts.append(alert)

    alerts.sort(key=lambda a: (
        {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}[a["severity"]],
        -a["consensus_score"],
    ))

    logger.info(
        "Generated %d alerts (%d CRITICAL, %d HIGH)",
        len(alerts),
        sum(1 for a in alerts if a["severity"] == "CRITICAL"),
        sum(1 for a in alerts if a["severity"] == "HIGH"),
    )
    return alerts


def alerts_to_json(alerts: list[dict], path: str) -> None:
    """Write alerts to a JSON file."""
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_alerts": len(alerts),
        "alerts": alerts,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Alerts written to %s", path)


def alerts_to_markdown(alerts: list[dict]) -> str:
    """Render alerts as a Markdown summary."""
    if not alerts:
        return "## Anomaly Detection Report\n\nNo anomalies detected.\n"

    lines = [
        "## Anomaly Detection Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
        f"**{len(alerts)} anomalies detected**\n",
        "| Severity | Ticker | Date | Close | Score | Description |",
        "|----------|--------|------|-------|-------|-------------|",
    ]

    for a in alerts:
        desc = a["description"][:90] + "..." if len(a["description"]) > 90 else a["description"]
        lines.append(
            f"| {a['severity']} | **{a['ticker']}** | {a['date']} "
            f"| ${a['close']:,.2f} | {a['consensus_score']:.3f} | {desc} |"
        )

    return "\n".join(lines) + "\n"
