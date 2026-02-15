"""Signal generation — Cool Runnings style.

"Feel the rhythm, feel the rhyme, get on up, it's bobsled time!"

This is where the science becomes human. Four detection methods run
independently, and this module translates their output into plain-English
alerts that anyone can understand — no deliverability jargon, no acronyms,
just clear guidance on what needs attention and what to do about it.

Signal levels (mapped to the Cool Runnings chant):
  WATCH:        "Peace Be the Journey" — monitoring, nothing to do yet
  HEADS_UP:     "Feel the Rhythm" — the rhythm of spam rate changed
  ATTENTION:    "Feel the Rhyme" — an unprecedented pattern appeared
  WARNING:      "Get on Up" — multiple independent tests agree
  URGENT:       "It's Bobsled Time" — clear momentum, time to act NOW
  CRITICAL:     "Sanka, Ya Dead?" — warned before, ignored, now worse

Supports incremental processing: new alerts merge with previously saved
alerts so the dashboard accumulates history across runs.
"""

import json
import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .config import GOOGLE_THRESHOLDS

logger = logging.getLogger(__name__)

# --- Signal types, colors, and Cool Runnings taglines ---
SIGNAL_CONFIG = {
    "WATCH": {
        "color": "#90CAF9",
        "label": "Watch",
        "tagline": "Peace Be the Journey",
        "icon": "visibility",
    },
    "HEADS_UP": {
        "color": "#FED100",
        "label": "Heads Up",
        "tagline": "Feel the Rhythm",
        "icon": "music_note",
    },
    "ATTENTION": {
        "color": "#FF6D00",
        "label": "Attention",
        "tagline": "Feel the Rhyme",
        "icon": "notification_important",
    },
    "WARNING": {
        "color": "#E65100",
        "label": "Warning",
        "tagline": "Get on Up",
        "icon": "warning",
    },
    "URGENT": {
        "color": "#D50000",
        "label": "Urgent",
        "tagline": "It's Bobsled Time",
        "icon": "local_fire_department",
    },
    "CRITICAL": {
        "color": "#B71C1C",
        "label": "Critical",
        "tagline": "Sanka, Ya Dead?",
        "icon": "emergency",
    },
}


def _google_threshold_context(spam_rate: float) -> str:
    """Describe where this spam rate falls relative to Google's thresholds."""
    pct = spam_rate * 100
    if spam_rate <= GOOGLE_THRESHOLDS["good"]:
        return f"Spam rate is {pct:.2f}% — below Google's 0.10% ideal threshold. Looking healthy."
    elif spam_rate <= GOOGLE_THRESHOLDS["monitor"]:
        return f"Spam rate is {pct:.2f}% — within Google's tolerance but above the 0.10% ideal."
    elif spam_rate <= GOOGLE_THRESHOLDS["concern"]:
        return f"Spam rate is {pct:.2f}% — above Google's 0.30% threshold. Google is watching."
    elif spam_rate <= GOOGLE_THRESHOLDS["problem"]:
        return f"Spam rate is {pct:.2f}% — approaching Google's 1% danger zone. This needs work."
    elif spam_rate <= GOOGLE_THRESHOLDS["critical"]:
        return f"Spam rate is {pct:.2f}% — above 1%. Google considers this a serious problem."
    else:
        return f"Spam rate is {pct:.2f}% — above 3%. Deliverability is at significant risk."


def _derive_signal(row: pd.Series, previous_domains: set) -> tuple[str, str]:
    """Derive an actionable signal from an anomaly row.

    Returns (signal_type, confidence).
    """
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    n_methods = int(row.get("methods_flagged", 0))
    fourier_flag = bool(row.get("fourier_anomaly", False))
    mp_flag = bool(row.get("mp_anomaly", False))
    ensemble_flag = bool(row.get("ensemble_anomaly", False))
    ewma_flag = bool(row.get("ewma_anomaly", False))
    domain = row["Domain"]

    confidence = "Strong" if n_methods >= 3 else "Moderate" if n_methods >= 2 else "Developing"

    # CRITICAL: Domain was previously warned and is STILL anomalous
    if domain in previous_domains and n_methods >= 2:
        return "CRITICAL", "Strong"

    # URGENT: EWMA fires with strong upward momentum (spam rate accelerating UP)
    # "It's Bobsled Time" — momentum is locked in
    if ewma_flag and dev > 5 and traj in ("accelerating", "breakout") and n_methods >= 2:
        return "URGENT", confidence

    # WARNING: 3+ methods agree OR ensemble + another method
    # "Get on Up" — multiple tests independently confirm
    if n_methods >= 3:
        return "WARNING", "Strong"
    if ensemble_flag and n_methods >= 2:
        return "WARNING", confidence

    # ATTENTION: Matrix Profile fires — unprecedented pattern
    # "Feel the Rhyme" — this is a new verse
    if mp_flag and n_methods >= 2:
        return "ATTENTION", confidence

    # HEADS_UP: Fourier fires — rhythm has changed
    # "Feel the Rhythm" — something shifted
    if fourier_flag and mp_flag:
        return "ATTENTION", confidence
    if fourier_flag:
        return "HEADS_UP", "Developing"

    # WATCH: Any anomaly detected but no clear signal yet
    return "WATCH", confidence


def _describe_signal(row: pd.Series, signal: str, confidence: str) -> str:
    """Generate a plain-English description for a signal.

    No deliverability jargon. Just tell them what's happening and what to do.
    """
    domain = row["Domain"]
    spam_rate = row.get("SpamRate", 0)
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    ewma_val = row.get("ewma_value", 0)
    n_methods = int(row.get("methods_flagged", 0))

    spam_pct = spam_rate * 100
    ewma_pct = ewma_val * 100
    direction = "above" if dev > 0 else "below"
    abs_dev = abs(dev)

    # Google threshold context
    threshold_note = _google_threshold_context(spam_rate)

    if signal == "CRITICAL":
        return (
            f"Sanka, ya dead?! I flagged {domain} before and nothing was done. "
            f"The spam rate is now {spam_pct:.2f}% — that's {abs_dev:.0f}% {direction} "
            f"its recent trend ({ewma_pct:.2f}%). {threshold_note} "
            f"Drop what you're doing and look at this domain. Review your sending practices, "
            f"check list hygiene, and investigate what changed. This isn't going away on its own."
        )

    if signal == "URGENT":
        return (
            f"It's bobsled time! {domain}'s spam rate is accelerating in the wrong direction. "
            f"Currently at {spam_pct:.2f}%, which is {abs_dev:.0f}% {direction} its trend "
            f"({ewma_pct:.2f}%) and the momentum is building. {threshold_note} "
            f"Act now: review recent campaign changes, check list quality, "
            f"and consider reducing volume until the trend reverses."
        )

    if signal == "WARNING":
        methods = []
        if row.get("fourier_anomaly"):
            methods.append("the rhythm of spam reports changed")
        if row.get("mp_anomaly"):
            methods.append("the pattern is unprecedented")
        if row.get("ensemble_anomaly"):
            methods.append("three statistical tests flag it")
        if row.get("ewma_anomaly"):
            methods.append("the trend momentum is abnormal")
        method_str = ", ".join(methods) if methods else "multiple detection methods agree"

        return (
            f"Get on up! {domain} needs attention — {n_methods} independent detection "
            f"methods agree something is off. Specifically: {method_str}. "
            f"Spam rate is {spam_pct:.2f}% ({abs_dev:.0f}% {direction} trend). "
            f"{threshold_note} "
            f"Investigate what changed recently: new content, new lists, send frequency, "
            f"or infrastructure changes."
        )

    if signal == "ATTENTION":
        return (
            f"Feel the rhyme... {domain}'s spam rate is doing something it hasn't done before. "
            f"Currently at {spam_pct:.2f}% ({abs_dev:.0f}% {direction} trend at {ewma_pct:.2f}%). "
            f"{threshold_note} "
            f"This domain needs your attention. Look at what's different about recent sends "
            f"compared to the last few weeks."
        )

    if signal == "HEADS_UP":
        return (
            f"Feel the rhythm... something shifted in {domain}'s spam rate pattern. "
            f"The usual rhythm of spam reports has changed. Currently at {spam_pct:.2f}% "
            f"({abs_dev:.0f}% {direction} trend). {threshold_note} "
            f"Not an emergency yet, but keep an eye on this domain over the next few days."
        )

    # WATCH
    parts = []
    if row.get("fourier_anomaly"):
        parts.append("the spam rate rhythm shifted slightly")
    if row.get("mp_anomaly"):
        parts.append("there's an unusual pattern forming")
    if row.get("ensemble_anomaly"):
        parts.append("statistical tests picked up something")
    if row.get("ewma_anomaly"):
        parts.append("there's a small trend deviation")
    detail = " and ".join(parts) if parts else "the anomaly score is slightly elevated"

    return (
        f"Peace be the journey. {domain} is on the radar because {detail}. "
        f"Spam rate is {spam_pct:.2f}% ({abs_dev:.0f}% {direction} trend). "
        f"{threshold_note} "
        f"No action needed yet — we'll keep watching."
    )


def generate_alerts(
    results: pd.DataFrame,
    previous_alerts: list[dict] | None = None,
    top_n: int = 100,
) -> list[dict]:
    """Generate structured spam rate signals from detection results."""
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    anomalies = results[results["consensus_anomaly"]].copy()
    if anomalies.empty:
        logger.info("No anomalies detected. Peace be the journey.")
        return []

    # Build set of previously warned domains for CRITICAL escalation
    previous_domains = set()
    if previous_alerts:
        for pa in previous_alerts:
            if pa.get("signal") in ("WARNING", "URGENT", "CRITICAL", "ATTENTION"):
                previous_domains.add(pa.get("domain", ""))

    # Keep the most recent anomaly per domain + any high-severity ones
    latest_per_domain = anomalies.sort_values("Date").groupby("Domain").tail(1)
    high_severity = anomalies[anomalies["methods_flagged"] >= 3]
    combined = pd.concat([latest_per_domain, high_severity]).drop_duplicates(subset=["Domain", "Date"])
    combined = combined.sort_values("consensus_score", ascending=False)

    alerts = []
    for _, row in combined.head(top_n).iterrows():
        n_methods = int(row.get("methods_flagged", 0))
        signal, confidence = _derive_signal(row, previous_domains)

        alert = {
            "domain": row["Domain"],
            "display": row["Domain"],
            "date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"]),
            "spam_rate": round(float(row["SpamRate"]), 6),
            "spam_rate_pct": f"{row['SpamRate'] * 100:.2f}%",
            "signal": signal,
            "signal_label": SIGNAL_CONFIG[signal]["label"],
            "signal_color": SIGNAL_CONFIG[signal]["color"],
            "signal_tagline": SIGNAL_CONFIG[signal]["tagline"],
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
                "ewma_value": round(float(row.get("ewma_value", 0)), 6),
            },
        }
        alerts.append(alert)

    # Sort: newest date first, then by consensus score
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


def merge_alerts(
    new_alerts: list[dict],
    previous_alerts: list[dict],
    max_alerts: int = 200,
) -> list[dict]:
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
    merged = list(new_alerts)
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
        "system": "Cool Runnings Spam Rate Monitor",
        "total_signals": len(alerts),
        "new_signals": n_new,
        "signals": alerts,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Signals written to %s (%d new, %d total)", path, n_new, len(alerts))


def alerts_to_markdown(alerts: list[dict]) -> str:
    """Render signals as a Markdown summary — Cool Runnings style."""
    if not alerts:
        return (
            "## Cool Runnings Spam Rate Report\n\n"
            "Peace be the journey. No anomalies detected.\n"
        )

    lines = [
        "## Cool Runnings Spam Rate Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
        '"Feel the rhythm, feel the rhyme, get on up, it\'s bobsled time!"\n',
        f"**{len(alerts)} signals generated**\n",
        "| Signal | Tagline | Domain | Date | Spam Rate | Score | What's Happening |",
        "|--------|---------|--------|------|-----------|-------|------------------|",
    ]

    for a in alerts:
        desc = a["description"][:80] + "..." if len(a["description"]) > 80 else a["description"]
        lines.append(
            f"| {a['signal_label']} | *{a['signal_tagline']}* | **{a['domain']}** | {a['date']} "
            f"| {a['spam_rate_pct']} | {a['consensus_score']:.3f} | {desc} |"
        )

    return "\n".join(lines) + "\n"
