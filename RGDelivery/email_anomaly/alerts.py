"""Signal generation — translates anomaly detection into actionable deliverability signals.

Signal types (from instructions.md):
  DROP signals (click rate below EWMA):
    WARM:        Decelerating drop — reduce volume, send to engaged only
    THROTTLE:    Accelerating drop — cut volume 70-90%, check auth
    PAUSE:       Breakout drop — halt sends, full diagnostic
    INVESTIGATE: Fourier + MP both flag — check ISP/ESP/DNS changes

  SPIKE signals (click rate above EWMA):
    AUDIT:       Decelerating spike — filter bot clicks from data
    QUARANTINE:  Accelerating spike — isolate segment, investigate source
    LOCKDOWN:    Breakout spike — freeze automated flows, verify systems

  Ambiguous:
    WATCH:       Anomaly detected but no clear direction

Supports incremental processing: new alerts merge with previously saved alerts
so that the dashboard accumulates history across runs.
"""

import json
import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --- Signal types and their meaning ---
SIGNAL_CONFIG = {
    "WARM":        {"color": "#00C853", "icon": "thermostat",     "label": "Warm"},
    "THROTTLE":    {"color": "#FF6D00", "icon": "speed",          "label": "Throttle"},
    "PAUSE":       {"color": "#D50000", "icon": "pause_circle",   "label": "Pause"},
    "INVESTIGATE": {"color": "#7C4DFF", "icon": "search",         "label": "Investigate"},
    "AUDIT":       {"color": "#F9A825", "icon": "fact_check",     "label": "Audit"},
    "QUARANTINE":  {"color": "#FF8F00", "icon": "shield",         "label": "Quarantine"},
    "LOCKDOWN":    {"color": "#D50000", "icon": "lock",           "label": "Lockdown"},
    "WATCH":       {"color": "#42A5F5", "icon": "visibility",     "label": "Watch"},
}


def _derive_signal(row: pd.Series) -> tuple[str, str]:
    """Derive an actionable deliverability signal from an anomaly row.

    Returns (signal_type, confidence) where confidence is
    'Strong', 'Moderate', or 'Developing'.
    """
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    n_methods = int(row.get("methods_flagged", 0))
    fourier_flag = bool(row.get("fourier_anomaly", False))
    mp_flag = bool(row.get("mp_anomaly", False))

    confidence = "Strong" if n_methods >= 3 else "Moderate" if n_methods >= 2 else "Developing"

    # --- Structural regime change (Fourier + Matrix Profile agree) ---
    if fourier_flag and mp_flag:
        return "INVESTIGATE", confidence

    # --- DROP signals: click rate below trend ---
    if dev < -8 and traj == "breakout" and n_methods >= 2:
        return "PAUSE", confidence
    if dev < -5 and traj in ("accelerating",) and n_methods >= 2:
        return "THROTTLE", confidence
    if dev < -8 and traj in ("decelerating", "normal") and n_methods >= 2:
        return "WARM", confidence
    if dev < -5 and traj == "decelerating" and n_methods >= 2:
        return "WARM", confidence

    # --- SPIKE signals: click rate above trend ---
    if dev > 8 and traj == "breakout" and n_methods >= 2:
        return "LOCKDOWN", confidence
    if dev > 5 and traj in ("accelerating",) and n_methods >= 2:
        return "QUARANTINE", confidence
    if dev > 8 and traj in ("decelerating", "normal") and n_methods >= 2:
        return "AUDIT", confidence
    if dev > 5 and traj == "decelerating" and n_methods >= 2:
        return "AUDIT", confidence

    # --- Fallback for deep deviations ---
    if dev < -8 and n_methods >= 2:
        return "WARM", "Developing"
    if dev > 8 and n_methods >= 2:
        return "AUDIT", "Developing"

    return "WATCH", confidence


def _describe_signal(row: pd.Series, signal: str, confidence: str) -> str:
    """Generate a plain-English actionable description for a signal."""
    domain = row["Domain"]
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    ewma_val = row.get("ewma_value", 0)
    clicks = row.get("Clicks", 0)
    n_methods = int(row.get("methods_flagged", 0))

    direction = "above" if dev > 0 else "below"
    abs_dev = abs(dev)

    if abs_dev > 1:
        position = f"{domain} is clicking {abs_dev:.1f}% {direction} its 20-day moving average ({ewma_val:,.0f} clicks)"
    else:
        position = f"{domain} is near its 20-day click average"

    if signal == "WARM":
        rationale = "Click rate decline is stabilizing — reputation damage may be bottoming."
        action = f"Reduce volume 40-60%. Shift to most engaged segments only. Monitor 3-5 send cycles before restoring volume."

    elif signal == "THROTTLE":
        rationale = "Click rate is actively collapsing — the domain may be under active penalization."
        action = "Cut volume 70-90% immediately. Halt sends to unengaged segments. Check SPF/DKIM/DMARC and blocklist status. Escalate to deliverability team."

    elif signal == "PAUSE":
        rationale = "Extreme click-rate collapse detected. This is a structural break — possible blocklisting, spam trap hit, or authentication failure."
        action = "Pause all campaigns immediately. Run full diagnostic: blocklist check, Google Postmaster review, authentication audit. Do not resume until root cause is identified."

    elif signal == "INVESTIGATE":
        rationale = "Both frequency analysis and pattern matching detect a structural regime change. The click engagement rhythm has fundamentally shifted."
        action = "Check for ISP policy changes, ESP platform issues, DNS/authentication changes. Cross-reference against industry news and ESP status pages."

    elif signal == "AUDIT":
        rationale = "Click spike is likely bot contamination — security scanners may be prefetching links."
        action = "Analyze click timing distribution for bot signatures. Check user-agent strings for scanners (Barracuda, Mimecast, Proofpoint). Filter contaminated data before segmentation decisions."

    elif signal == "QUARANTINE":
        rationale = "Accelerating click spike without proportional conversion lift suggests escalating contamination or list attack."
        action = "Quarantine affected segment from engagement-based decisioning. Investigate list bombing, link scanner deployment, or compromised tracking domain."

    elif signal == "LOCKDOWN":
        rationale = "Extreme click spike breaks all historical patterns — possible system malfunction or deliberate attack."
        action = "Freeze all automated engagement-based sends. Check for list bombing pattern. Verify tracking pixel/link integrity. Review for compromised API keys."

    else:  # WATCH
        parts = []
        if row.get("fourier_anomaly"):
            parts.append("engagement rhythm has shifted")
        if row.get("mp_anomaly"):
            parts.append("click pattern is unprecedented")
        if row.get("ensemble_anomaly"):
            parts.append("statistical tests flag unusual behavior")
        detail = " and ".join(parts) if parts else "anomaly score is elevated"
        rationale = f"Detection methods flagged this because {detail}, but no clear directional signal has emerged yet."
        action = "Monitor next 2-3 send cycles. If anomaly persists, re-evaluate."

    return f"{position}. {rationale} {action}"


def generate_alerts(results: pd.DataFrame, top_n: int = 50) -> list[dict]:
    """Generate structured deliverability signals from detection results."""
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    anomalies = results[results["consensus_anomaly"]].copy()
    if anomalies.empty:
        logger.info("No anomalies detected.")
        return []

    # Keep the most recent anomaly per domain + any high-severity historical ones
    latest_per_domain = anomalies.sort_values("Date").groupby("Domain").tail(1)
    high_severity = anomalies[anomalies["methods_flagged"] >= 3]
    combined = pd.concat([latest_per_domain, high_severity]).drop_duplicates(subset=["Domain", "Date"])
    combined = combined.sort_values("consensus_score", ascending=False)

    alerts = []
    for _, row in combined.head(top_n).iterrows():
        n_methods = int(row.get("methods_flagged", 0))
        signal, confidence = _derive_signal(row)

        alert = {
            "domain": row["Domain"],
            "display": row["Domain"],
            "date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"]),
            "clicks": int(row["Clicks"]),
            "signal": signal,
            "signal_label": SIGNAL_CONFIG[signal]["label"],
            "signal_color": SIGNAL_CONFIG[signal]["color"],
            "confidence": confidence,
            "methods_flagged": n_methods,
            "consensus_score": round(float(row["consensus_score"]), 4),
            "description": _describe_signal(row, signal, confidence),
            "run_date": run_date,
            "is_new": True,
            "first_detected": run_date,
            "details": {
                "fourier_score": round(float(row.get("fourier_score", 0)), 4),
                "mp_score": round(float(row.get("mp_score", 0)), 4),
                "ensemble_score": round(float(row.get("ensemble_score", 0)), 4),
                "ewma_score": round(float(row.get("ewma_score", 0)), 4),
                "trajectory": row.get("trajectory", "normal"),
                "deviation_pct": round(float(row.get("deviation_pct", 0)), 2),
                "ewma_value": round(float(row.get("ewma_value", 0)), 2),
            },
        }
        alerts.append(alert)

    # Sort: newest date first (most recent signals at top), then by consensus score
    alerts.sort(key=lambda a: (a["date"], a["consensus_score"]), reverse=True)

    logger.info(
        "Generated %d signals (%d actionable, %d watch)",
        len(alerts),
        sum(1 for a in alerts if a["signal"] != "WATCH"),
        sum(1 for a in alerts if a["signal"] == "WATCH"),
    )
    return alerts


def load_previous_alerts(path: str) -> list[dict]:
    """Load previously saved alerts from a JSON file, if it exists."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        previous = data.get("signals", [])
        logger.info("Loaded %d previous alerts from %s", len(previous), path)
        return previous
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Could not parse previous alerts from %s — starting fresh", path)
        return []


def merge_alerts(new_alerts: list[dict], previous_alerts: list[dict], max_alerts: int = 200) -> list[dict]:
    """Merge new alerts with previous alerts for incremental processing.

    - New alerts take precedence for the same (domain, date) pair.
    - Previous alerts that don't overlap are preserved with is_new=False.
    - Final list is sorted by date descending (newest first).
    - Capped at max_alerts to prevent unbounded growth.
    """
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Index new alerts by (domain, date) for fast lookup
    new_keys = {(a["domain"], a["date"]) for a in new_alerts}

    # Mark all previous alerts as not-new, preserve first_detected
    merged = list(new_alerts)  # new alerts already have is_new=True
    for prev in previous_alerts:
        key = (prev.get("domain"), prev.get("date"))
        if key not in new_keys:
            prev["is_new"] = False
            prev["run_date"] = prev.get("run_date", run_date)
            prev["first_detected"] = prev.get("first_detected", prev.get("date", run_date))
            merged.append(prev)
        else:
            # New alert takes precedence — but preserve first_detected from previous
            for new_a in new_alerts:
                if (new_a["domain"], new_a["date"]) == key:
                    new_a["first_detected"] = prev.get("first_detected", prev.get("date", run_date))
                    break

    # Sort: newest date first, then by consensus score descending
    merged.sort(key=lambda a: (a["date"], a.get("consensus_score", 0)), reverse=True)

    if len(merged) > max_alerts:
        merged = merged[:max_alerts]

    n_new = sum(1 for a in merged if a.get("is_new"))
    n_prev = len(merged) - n_new
    logger.info("Merged alerts: %d new + %d historical = %d total", n_new, n_prev, len(merged))
    return merged


def alerts_to_json(alerts: list[dict], path: str) -> None:
    """Write signals to a JSON file."""
    n_new = sum(1 for a in alerts if a.get("is_new"))
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_signals": len(alerts),
        "new_signals": n_new,
        "signals": alerts,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Signals written to %s (%d new, %d total)", path, n_new, len(alerts))


def alerts_to_markdown(alerts: list[dict]) -> str:
    """Render signals as a Markdown summary."""
    if not alerts:
        return "## Deliverability Signals Report\n\nNo anomalies detected.\n"

    lines = [
        "## Deliverability Signals Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
        f"**{len(alerts)} signals generated**\n",
        "| Signal | Confidence | Domain | Date | Clicks | Score | Description |",
        "|--------|-----------|--------|------|--------|-------|-------------|",
    ]

    for a in alerts:
        desc = a["description"][:90] + "..." if len(a["description"]) > 90 else a["description"]
        lines.append(
            f"| {a['signal_label']} | {a['confidence']} | **{a['domain']}** | {a['date']} "
            f"| {a['clicks']:,} | {a['consensus_score']:.3f} | {desc} |"
        )

    return "\n".join(lines) + "\n"
