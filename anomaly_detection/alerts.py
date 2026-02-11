"""Signal generation — translates anomaly detection into actionable trading signals.

Supports incremental processing: new alerts merge with previously saved alerts
so that the dashboard accumulates history across runs.
"""

import json
import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .config import TICKER_NAMES, ticker_display

logger = logging.getLogger(__name__)

# --- Signal types and their meaning ---
# BUY:   Mean-reversion long — oversold, selling pressure fading
# SELL:  Mean-reversion exit — overbought, buying pressure fading
# LONG:  Momentum long — accelerating upward breakout
# SHORT: Momentum short — accelerating downward breakdown
# REDUCE: Regime change — structural break, reduce exposure
# WATCH: Anomaly detected but no clear directional signal yet

SIGNAL_CONFIG = {
    "BUY":    {"color": "#00C853", "icon": "arrow_upward",    "label": "Buy"},
    "SELL":   {"color": "#D50000", "icon": "arrow_downward",  "label": "Sell"},
    "LONG":   {"color": "#00897B", "icon": "trending_up",     "label": "Long"},
    "SHORT":  {"color": "#FF6D00", "icon": "trending_down",   "label": "Short"},
    "REDUCE": {"color": "#F9A825", "icon": "warning",         "label": "Reduce Exposure"},
    "WATCH":  {"color": "#42A5F5", "icon": "visibility",      "label": "Watch"},
}


def _derive_signal(row: pd.Series) -> tuple[str, str]:
    """Derive an actionable trading signal from an anomaly row.

    Returns (signal_type, confidence) where confidence is
    'Strong', 'Moderate', or 'Developing'.
    """
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    n_methods = int(row.get("methods_flagged", 0))
    fourier_flag = bool(row.get("fourier_anomaly", False))
    mp_flag = bool(row.get("mp_anomaly", False))

    confidence = "Strong" if n_methods >= 3 else "Moderate" if n_methods >= 2 else "Developing"

    # --- Mean-reversion BUY: deeply oversold + selling exhaustion ---
    if dev < -8 and traj in ("decelerating", "normal") and n_methods >= 2:
        return "BUY", confidence
    if dev < -5 and traj == "decelerating" and n_methods >= 2:
        return "BUY", confidence

    # --- Mean-reversion SELL: deeply overbought + buying exhaustion ---
    if dev > 8 and traj in ("decelerating", "normal") and n_methods >= 2:
        return "SELL", confidence
    if dev > 5 and traj == "decelerating" and n_methods >= 2:
        return "SELL", confidence

    # --- Momentum SHORT: accelerating decline ---
    if dev < -3 and traj in ("accelerating", "breakout") and n_methods >= 2:
        return "SHORT", confidence

    # --- Momentum LONG: accelerating rally ---
    if dev > 3 and traj in ("accelerating", "breakout") and n_methods >= 2:
        return "LONG", confidence

    # --- Structural regime change (Fourier + Matrix Profile agree) ---
    if fourier_flag and mp_flag:
        return "REDUCE", confidence

    # --- Overbought/oversold without clear trajectory ---
    if dev < -8 and n_methods >= 2:
        return "BUY", "Developing"
    if dev > 8 and n_methods >= 2:
        return "SELL", "Developing"

    return "WATCH", confidence


def _describe_signal(row: pd.Series, signal: str, confidence: str) -> str:
    """Generate a plain-English actionable description for a signal."""
    ticker = row["Ticker"]
    display = ticker_display(ticker)
    dev = row.get("deviation_pct", 0)
    traj = row.get("trajectory", "normal")
    ewma_val = row.get("ewma_value", 0)
    close = row.get("Close", 0)
    n_methods = int(row.get("methods_flagged", 0))

    direction = "above" if dev > 0 else "below"
    abs_dev = abs(dev)

    # Build the core observation
    if abs_dev > 1:
        position = f"{display} is trading {abs_dev:.1f}% {direction} its 20-day moving average (${ewma_val:,.2f})"
    else:
        position = f"{display} is near its 20-day moving average"

    # Build the action rationale
    if signal == "BUY":
        if traj == "decelerating":
            rationale = "Selling pressure is fading, suggesting a potential bounce back toward the trend line."
        else:
            rationale = f"The stock appears oversold at {n_methods} standard deviations from normal. Mean-reversion toward ${ewma_val:,.2f} is likely."
        action = f"Consider entering a long position targeting the ${ewma_val:,.2f} moving average."

    elif signal == "SELL":
        if traj == "decelerating":
            rationale = "Buying momentum is exhausting, suggesting the rally may be losing steam."
        else:
            rationale = f"The stock appears overbought at {n_methods} standard deviations from normal. A pullback toward ${ewma_val:,.2f} is likely."
        action = f"Consider taking profits or tightening stops. Fair value near ${ewma_val:,.2f}."

    elif signal == "LONG":
        rationale = "Upward momentum is accelerating with multiple detection methods confirming the move."
        action = "Consider a momentum-based long position with a trailing stop below the trend line."

    elif signal == "SHORT":
        rationale = "Downward momentum is accelerating with multiple detection methods confirming the decline."
        action = "Consider a short position or protective puts. Set stops above the recent high."

    elif signal == "REDUCE":
        rationale = "Both frequency analysis and pattern matching detect a structural regime change. The stock's behavior has shifted in a way that has no recent historical precedent."
        action = "Reduce position size until the new regime clarifies. Avoid new entries."

    else:  # WATCH
        parts = []
        if row.get("fourier_anomaly"):
            parts.append("trading rhythm has shifted")
        if row.get("mp_anomaly"):
            parts.append("price pattern is unprecedented")
        if row.get("ensemble_anomaly"):
            parts.append("statistical tests flag unusual behavior")
        detail = " and ".join(parts) if parts else "anomaly score is elevated"
        rationale = f"Detection methods flagged this because {detail}, but no clear directional signal has emerged yet."
        action = "Monitor for follow-through before taking a position."

    return f"{position}. {rationale} {action}"


def generate_alerts(results: pd.DataFrame, top_n: int = 50) -> list[dict]:
    """Generate structured trading signals from detection results."""
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    anomalies = results[results["consensus_anomaly"]].copy()
    if anomalies.empty:
        logger.info("No anomalies detected.")
        return []

    # Keep the most recent anomaly per ticker + any high-severity historical ones
    latest_per_ticker = anomalies.sort_values("Date").groupby("Ticker").tail(1)
    high_severity = anomalies[anomalies["methods_flagged"] >= 3]
    combined = pd.concat([latest_per_ticker, high_severity]).drop_duplicates(subset=["Ticker", "Date"])
    combined = combined.sort_values("consensus_score", ascending=False)

    alerts = []
    for _, row in combined.head(top_n).iterrows():
        n_methods = int(row.get("methods_flagged", 0))
        signal, confidence = _derive_signal(row)

        alert = {
            "ticker": row["Ticker"],
            "ticker_name": TICKER_NAMES.get(row["Ticker"], row["Ticker"]),
            "display": ticker_display(row["Ticker"]),
            "date": row["Date"].strftime("%Y-%m-%d") if hasattr(row["Date"], "strftime") else str(row["Date"]),
            "close": round(float(row["Close"]), 2),
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
        sum(1 for a in alerts if a["signal"] not in ("WATCH", "REDUCE")),
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

    - New alerts take precedence for the same (ticker, date) pair.
    - Previous alerts that don't overlap are preserved with is_new=False.
    - Final list is sorted by date descending (newest first).
    - Capped at max_alerts to prevent unbounded growth.
    """
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Index new alerts by (ticker, date) for fast lookup
    new_keys = {(a["ticker"], a["date"]) for a in new_alerts}

    # Mark all previous alerts as not-new, preserve first_detected
    merged = list(new_alerts)  # new alerts already have is_new=True
    for prev in previous_alerts:
        key = (prev.get("ticker"), prev.get("date"))
        if key not in new_keys:
            prev["is_new"] = False
            prev["run_date"] = prev.get("run_date", run_date)
            prev["first_detected"] = prev.get("first_detected", prev.get("date", run_date))
            merged.append(prev)
        else:
            # New alert takes precedence — but preserve first_detected from previous
            for new_a in new_alerts:
                if (new_a["ticker"], new_a["date"]) == key:
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
        return "## Trading Signals Report\n\nNo anomalies detected.\n"

    lines = [
        "## Trading Signals Report",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
        f"**{len(alerts)} signals generated**\n",
        "| Signal | Confidence | Ticker | Date | Close | Score | Description |",
        "|--------|-----------|--------|------|-------|-------|-------------|",
    ]

    for a in alerts:
        desc = a["description"][:90] + "..." if len(a["description"]) > 90 else a["description"]
        lines.append(
            f"| {a['signal_label']} | {a['confidence']} | **{a['display']}** | {a['date']} "
            f"| ${a['close']:,.2f} | {a['consensus_score']:.3f} | {desc} |"
        )

    return "\n".join(lines) + "\n"
