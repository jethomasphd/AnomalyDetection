"""Signal generation — translates anomaly detection into actionable trading signals.

Derivation operates in standardized units (dev_z = the EWMA deviation divided
by its own trailing volatility, per ticker), so "stretched" means the same
thing for every ticker, plus an absolute materiality gate so statistically
unusual but economically meaningless moves (a 0.1% wiggle in a T-bill ETF)
can never become trade calls.

Supports incremental processing: new alerts merge with previously saved
alerts so the dashboard accumulates history across runs. The full immutable
record lives in the signals ledger; alerts.json is a capped display view.
"""

import json
import logging
import os
from datetime import datetime

import pandas as pd

from .config import (
    SENSITIVITY_PRESETS,
    TICKER_NAMES,
    TRADE_MIN_ABS_DEVIATION_PCT,
    ticker_display,
)

logger = logging.getLogger(__name__)

# --- Signal types and their meaning ---
# BUY:   Mean-reversion long — deeply stretched below trend, stretch no longer growing
# SELL:  Mean-reversion exit — deeply stretched above trend, stretch no longer growing
# LONG:  Momentum long — stretched above trend and still extending/breaking out
# SHORT: Momentum short — stretched below trend and still extending/breaking out
# REDUCE: Regime change — structural break (Fourier + Matrix Profile agree)
# WATCH: Anomaly detected but no tradable directional setup

SIGNAL_CONFIG = {
    "BUY":    {"color": "#00C853", "icon": "arrow_upward",    "label": "Buy"},
    "SELL":   {"color": "#D50000", "icon": "arrow_downward",  "label": "Sell"},
    "LONG":   {"color": "#00897B", "icon": "trending_up",     "label": "Long"},
    "SHORT":  {"color": "#FF6D00", "icon": "trending_down",   "label": "Short"},
    "REDUCE": {"color": "#F9A825", "icon": "warning",         "label": "Reduce Exposure"},
    "WATCH":  {"color": "#42A5F5", "icon": "visibility",      "label": "Watch"},
}


def derivation_thresholds(sensitivity: str) -> dict:
    """Sigma thresholds used by signal derivation, per sensitivity.

    reversion_z: |dev_z| needed for a mean-reversion BUY/SELL.
    momentum_z:  |dev_z| needed for a momentum LONG/SHORT (lower, because
                 the trajectory — extending/breakout — provides the
                 confirmation that reversion setups get from magnitude).
    """
    z = SENSITIVITY_PRESETS[sensitivity]["z_threshold"]
    return {"reversion_z": z, "momentum_z": max(1.5, z - 1.0)}


def _derive_signal(row: pd.Series, sensitivity: str = "medium") -> tuple[str, str]:
    """Derive an actionable trading signal from a consensus-anomaly row.

    Returns (signal_type, confidence) where confidence is
    'Strong', 'Moderate', or 'Developing'.

    Rules (dev_z = EWMA deviation in units of its own trailing sigma), in
    two regimes split by what the stretch is DOING:

      breakout (climactic extreme)      -> FADE the move (overreaction
        BUY  if dev_z <= -reversion_z      reversal: extreme washouts and
        SELL if dev_z >= +reversion_z      blowoffs revert, on average)

      extending (stretch still building) -> RIDE the move
        LONG  if dev_z >= +momentum_z
        SHORT if dev_z <= -momentum_z

      reverting/stable (stretch fading)  -> reversion already under way
        BUY  if dev_z <= -reversion_z
        SELL if dev_z >= +reversion_z

      REDUCE  Fourier AND Matrix Profile both flag (structural change)
      WATCH   anything else

    The fade-the-breakout rule is calibrated to the measured resolution of
    extreme stretches in this universe (see HOW_IT_WORKS.md): bars more
    than ~3.5 sigma below trend rebounded ~+2-3% over the following 10
    sessions on average, so shorting a capitulation — what a naive
    momentum rule does — is systematically wrong-way.

    Tradable signals additionally require at least 2 methods in agreement
    and the materiality gate: |deviation_pct| >= TRADE_MIN_ABS_DEVIATION_PCT.
    """
    thresholds = derivation_thresholds(sensitivity)
    dev_z = float(row.get("dev_z", 0) or 0)
    dev_pct = float(row.get("deviation_pct", 0) or 0)
    traj = row.get("trajectory", "stable")
    n_methods = int(row.get("methods_flagged", 0))
    fourier_flag = bool(row.get("fourier_anomaly", False))
    mp_flag = bool(row.get("mp_anomaly", False))

    confidence = "Strong" if n_methods >= 3 else "Moderate" if n_methods >= 2 else "Developing"

    material = abs(dev_pct) >= TRADE_MIN_ABS_DEVIATION_PCT
    tradable = material and n_methods >= 2

    if tradable:
        if traj == "breakout":
            # Climactic extreme: fade it (overreaction reversal).
            if dev_z <= -thresholds["reversion_z"]:
                return "BUY", confidence
            if dev_z >= thresholds["reversion_z"]:
                return "SELL", confidence
        elif traj == "extending":
            # Momentum still building (not yet climactic): ride it.
            if dev_z >= thresholds["momentum_z"]:
                return "LONG", confidence
            if dev_z <= -thresholds["momentum_z"]:
                return "SHORT", confidence
        else:  # reverting / stable
            if dev_z <= -thresholds["reversion_z"]:
                return "BUY", confidence
            if dev_z >= thresholds["reversion_z"]:
                return "SELL", confidence

    if fourier_flag and mp_flag:
        return "REDUCE", confidence

    return "WATCH", confidence


def _describe_signal(row: pd.Series, signal: str, confidence: str) -> str:
    """Generate a plain-English, numerically honest description for a signal."""
    ticker = row["Ticker"]
    display = ticker_display(ticker)
    dev_pct = float(row.get("deviation_pct", 0) or 0)
    dev_z = float(row.get("dev_z", 0) or 0)
    traj = row.get("trajectory", "stable")
    ewma_val = float(row.get("ewma_value", 0) or 0)
    n_methods = int(row.get("methods_flagged", 0))

    direction = "above" if dev_pct > 0 else "below"
    abs_dev = abs(dev_pct)
    abs_z = abs(dev_z)

    if abs_dev >= 1:
        position = (
            f"{display} is trading {abs_dev:.1f}% {direction} its 20-day trend "
            f"(${ewma_val:,.2f}) — a {abs_z:.1f}-sigma stretch for this ticker"
        )
    else:
        position = f"{display} is near its 20-day trend (${ewma_val:,.2f})"

    traj_text = {
        "reverting": "the stretch is contracting",
        "extending": "the stretch is still widening",
        "breakout": "the stretch is at breakout extremes",
        "stable": "the stretch is holding steady",
    }.get(traj, "")

    if signal == "BUY":
        if traj == "breakout":
            rationale = (
                f"A capitulation-grade washout: {traj_text}. Extreme downside stretches "
                f"of this size historically rebound toward trend. {n_methods} of 4 methods agree."
            )
        else:
            rationale = (
                f"Oversold relative to its own typical variability, and {traj_text} — "
                f"selling pressure is no longer building. {n_methods} of 4 methods agree."
            )
        action = f"Consider a mean-reversion long targeting the ${ewma_val:,.2f} trend line."
    elif signal == "SELL":
        if traj == "breakout":
            rationale = (
                f"A blowoff-grade extreme: {traj_text}. Stretches this far above trend "
                f"historically stall or revert. {n_methods} of 4 methods agree."
            )
        else:
            rationale = (
                f"Overbought relative to its own typical variability, and {traj_text} — "
                f"buying pressure is no longer building. {n_methods} of 4 methods agree."
            )
        action = f"Consider taking profits or tightening stops; trend value near ${ewma_val:,.2f}."
    elif signal == "LONG":
        rationale = (
            f"Upward momentum: {traj_text}, with {n_methods} of 4 methods confirming "
            f"the move is abnormal for this ticker."
        )
        action = "Consider a momentum long with a trailing stop below the trend line."
    elif signal == "SHORT":
        rationale = (
            f"Downward momentum: {traj_text}, with {n_methods} of 4 methods confirming "
            f"the move is abnormal for this ticker."
        )
        action = "Consider a short position or protective puts; stops above the recent high."
    elif signal == "REDUCE":
        rationale = (
            "Both frequency analysis and pattern matching detect a structural change: "
            "the stock's recent behavior has no precedent in its own history."
        )
        action = "Reduce position size until the new regime clarifies. Avoid new entries."
    else:  # WATCH
        parts = []
        if row.get("fourier_anomaly"):
            parts.append("its trading rhythm has shifted")
        if row.get("mp_anomaly"):
            parts.append("its price pattern is novel")
        if row.get("ensemble_anomaly"):
            parts.append("statistical tests flag unusual behavior")
        if row.get("ewma_anomaly"):
            parts.append("its trend deviation is abnormal")
        detail = " and ".join(parts) if parts else "the combined anomaly score is elevated"
        if abs(dev_pct) < TRADE_MIN_ABS_DEVIATION_PCT:
            gate = (
                f" The move is below the {TRADE_MIN_ABS_DEVIATION_PCT:.0f}% materiality "
                f"threshold, so no trade call is made."
            )
        else:
            gate = ""
        rationale = f"Flagged because {detail}, but there is no tradable directional setup.{gate}"
        action = "Monitor for follow-through before taking a position."

    return f"{position}. {rationale} {action}"


def generate_alerts(
    results: pd.DataFrame,
    sensitivity: str = "medium",
    provenance: str = "live",
    top_n: int = 2000,
) -> list[dict]:
    """Generate structured trading signals from detection results.

    Every consensus-anomaly bar in `results` produces one alert (the caller
    passes only NEW bars under edge-only operation, or the full history when
    backfilling). For provenance='backfill', run_date/detected_at are set to
    the BAR date — the causal detectors guarantee that verdict is what a
    live run that evening would have produced — and is_new is False.
    """
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    anomalies = results[results["consensus_anomaly"]].copy()
    if anomalies.empty:
        logger.info("No anomalies detected.")
        return []

    anomalies = anomalies.sort_values("consensus_score", ascending=False)
    if len(anomalies) > top_n:
        logger.warning(
            "Capping alerts at %d of %d consensus anomalies (safety valve)",
            top_n, len(anomalies),
        )
        anomalies = anomalies.head(top_n)

    alerts = []
    for _, row in anomalies.iterrows():
        n_methods = int(row.get("methods_flagged", 0))
        signal, confidence = _derive_signal(row, sensitivity=sensitivity)
        date_str = (
            row["Date"].strftime("%Y-%m-%d")
            if hasattr(row["Date"], "strftime")
            else str(row["Date"])[:10]
        )
        detected = date_str if provenance == "backfill" else run_date

        alert = {
            "ticker": row["Ticker"],
            "ticker_name": TICKER_NAMES.get(row["Ticker"], row["Ticker"]),
            "display": ticker_display(row["Ticker"]),
            "date": date_str,
            "close": round(float(row["Close"]), 2),
            "signal": signal,
            "signal_label": SIGNAL_CONFIG[signal]["label"],
            "signal_color": SIGNAL_CONFIG[signal]["color"],
            "confidence": confidence,
            "methods_flagged": n_methods,
            "consensus_score": round(float(row["consensus_score"]), 4),
            "description": _describe_signal(row, signal, confidence),
            "run_date": detected,
            "is_new": provenance == "live",
            "first_detected": detected,
            "detected_at": detected,
            "provenance": provenance,
            "details": {
                "fourier_score": round(float(row.get("fourier_score", 0)), 4),
                "mp_score": round(float(row.get("mp_score", 0)), 4),
                "ensemble_score": round(float(row.get("ensemble_score", 0)), 4),
                "ewma_score": round(float(row.get("ewma_score", 0)), 4),
                "trajectory": row.get("trajectory", "stable"),
                "deviation_pct": round(float(row.get("deviation_pct", 0)), 2),
                "dev_z": round(float(row.get("dev_z", 0) or 0), 2),
                "ewma_value": round(float(row.get("ewma_value", 0)), 2),
                # Frozen close at the detection-time price basis — the
                # anchor for basis reconciliation after corporate actions.
                "close": round(float(row["Close"]), 4),
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


def append_new_alerts(new_alerts: list[dict], previous_alerts: list[dict], max_alerts: int = 200) -> list[dict]:
    """Combine edge-detected new alerts with the frozen history.

    Edge-only detection guarantees new_alerts and previous_alerts have
    disjoint (ticker, date) keys by construction — there's no conflict to
    resolve. Previous alerts are marked is_new=False; the concatenated list
    is sorted newest-first and capped at max_alerts.

    The cap applies only to this DISPLAY view (alerts.json). The complete
    record lives in the signals ledger and is never truncated.

    If a conflicting (ticker, date) is somehow present (legacy data), the
    previous alert wins: the log is frozen, so the original verdict is
    preserved rather than overwritten.
    """
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    previous_keys = {(a.get("ticker"), a.get("date")) for a in previous_alerts}

    # Drop any new alert that collides with a frozen historical record
    kept_new = []
    dropped = 0
    for a in new_alerts:
        if (a["ticker"], a["date"]) in previous_keys:
            dropped += 1
            continue
        kept_new.append(a)
    if dropped:
        logger.warning(
            "Dropped %d new alerts that collided with frozen history (edge-only "
            "invariant violated — historical verdict preserved)", dropped,
        )

    combined = list(kept_new)
    for prev in previous_alerts:
        prev["is_new"] = False
        prev["run_date"] = prev.get("run_date", run_date)
        prev["first_detected"] = prev.get("first_detected", prev.get("date", run_date))
        prev["detected_at"] = prev.get("detected_at") or prev["first_detected"]
        combined.append(prev)

    combined.sort(key=lambda a: (a["date"], a.get("consensus_score", 0)), reverse=True)
    if len(combined) > max_alerts:
        combined = combined[:max_alerts]

    n_new = sum(1 for a in combined if a.get("is_new"))
    logger.info("Alerts: %d new-this-run + %d frozen-history = %d total (display view)",
                n_new, len(combined) - n_new, len(combined))
    return combined


# Back-compat alias (soft-deprecated): the name is kept so external callers
# don't break, but the new semantics are append-only. Remove after downstream
# updates land.
merge_alerts = append_new_alerts


def alerts_to_json(
    alerts: list[dict],
    path: str,
    run_info: dict | None = None,
    ticker_status: dict | None = None,
) -> None:
    """Write signals to a JSON file.

    `run_info` and `ticker_status` are recomputed VIEWS refreshed on every
    run, alongside the frozen signal rows:

      * run_info proves the model actually ran — how many new bars were
        scored and through which bar date. A quiet day (0 new signals) is
        then distinguishable from a job that only re-stamped the file.
      * ticker_status carries each ticker's current close/date, stale-feed
        flag, and any price-basis break, so a frozen close from weeks ago
        is never mistaken for the model's current price.
    """
    n_new = sum(1 for a in alerts if a.get("is_new"))
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "run": run_info or {},
        "total_signals": len(alerts),
        "new_signals": n_new,
        "ticker_status": ticker_status or {},
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
