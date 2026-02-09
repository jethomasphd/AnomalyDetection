"""Alert generation — produces human-readable summaries and structured JSON."""

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Severity mapping based on number of methods in agreement
SEVERITY_MAP = {
    4: "CRITICAL",
    3: "HIGH",
    2: "MODERATE",
    1: "LOW",
}

TRAJECTORY_LABELS = {
    "breakout": "Breakout — extreme deviation from trend",
    "accelerating": "Accelerating — momentum building",
    "decelerating": "Decelerating — momentum fading",
    "normal": "Normal",
}


def _describe_anomaly(row: pd.Series) -> str:
    """Generate a plain-English explanation for one anomaly."""
    parts = []
    methods = []

    if row.get("fourier_anomaly"):
        methods.append("Frequency Analysis")
        parts.append("trading rhythm has shifted from historical pattern")
    if row.get("mp_anomaly"):
        methods.append("Pattern Matching")
        parts.append("price pattern is unlike anything seen in recent history")
    if row.get("ensemble_anomaly"):
        methods.append("Statistical Ensemble")
        # Break down which components contributed
        components = []
        if row.get("zscore_component", 0) > 0.5:
            components.append("statistical outlier")
        if row.get("seasonal_component", 0) > 0.5:
            components.append("seasonal deviation")
        if row.get("iforest_component", 0) > 0.5:
            components.append("multivariate outlier")
        if components:
            parts.append(f"flagged as {', '.join(components)}")
        else:
            parts.append("multiple statistical tests flagged unusual activity")
    if row.get("ewma_anomaly"):
        methods.append("Trend Analysis")
        dev = row.get("deviation_pct", 0)
        direction = "above" if dev > 0 else "below"
        parts.append(f"price is {abs(dev):.1f}% {direction} its moving average")

    trajectory = row.get("trajectory", "normal")
    if trajectory != "normal":
        parts.append(TRAJECTORY_LABELS.get(trajectory, trajectory))

    detection_summary = "; ".join(parts) if parts else "Anomalous activity detected"
    method_list = ", ".join(methods) if methods else "Consensus"

    return f"[{method_list}] {detection_summary}"


def generate_alerts(
    results: pd.DataFrame,
    top_n: int = 50,
) -> list[dict]:
    """Generate structured alerts from detection results.

    Returns a list of alert dicts, sorted by severity then consensus score.
    """
    anomalies = results[results["consensus_anomaly"]].copy()

    if anomalies.empty:
        logger.info("No anomalies detected — no alerts generated.")
        return []

    # Focus on the most recent date per ticker if many anomalies
    anomalies = anomalies.sort_values("consensus_score", ascending=False)

    alerts = []
    for _, row in anomalies.head(top_n).iterrows():
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

    alerts.sort(key=lambda a: ({"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}[a["severity"]], -a["consensus_score"]))

    logger.info("Generated %d alerts (%d CRITICAL, %d HIGH)",
                len(alerts),
                sum(1 for a in alerts if a["severity"] == "CRITICAL"),
                sum(1 for a in alerts if a["severity"] == "HIGH"))
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
    """Render alerts as a Markdown summary table."""
    if not alerts:
        return "## Anomaly Detection Report\n\nNo anomalies detected.\n"

    lines = [
        "## Anomaly Detection Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
        f"**{len(alerts)} anomalies detected**\n",
        "| Severity | Ticker | Date | Close | Score | Methods | Description |",
        "|----------|--------|------|-------|-------|---------|-------------|",
    ]

    severity_badge = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MODERATE": "🟡 MODERATE",
        "LOW": "🔵 LOW",
    }

    for a in alerts:
        badge = severity_badge.get(a["severity"], a["severity"])
        desc = a["description"][:80] + "..." if len(a["description"]) > 80 else a["description"]
        lines.append(
            f"| {badge} | **{a['ticker']}** | {a['date']} | ${a['close']:,.2f} "
            f"| {a['consensus_score']:.3f} | {a['methods_flagged']}/4 | {desc} |"
        )

    return "\n".join(lines) + "\n"
