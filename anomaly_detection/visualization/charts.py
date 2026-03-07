"""Chart generation — clean Plotly figures for the dashboard.

IMPORTANT: All charts use fig.to_plotly_json() (not fig.to_json()) to produce
plain-array JSON compatible with the Plotly.js CDN version loaded in the browser.
Plotly >=6 defaults to binary-encoded 'bdata' in to_json(), which older Plotly.js
cannot decode — causing markers and data to appear at y=0 (on the x-axis).
"""

import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import TICKER_NAMES, TICKER_REGISTRY, ticker_display

logger = logging.getLogger(__name__)

# --- Dark terminal color palette ---
NEON_GREEN = "#00E676"
NEON_BLUE = "#00B0FF"
NEON_RED = "#FF1744"
NEON_ORANGE = "#FF9100"
NEON_AMBER = "#FFD600"
NEON_TEAL = "#1DE9B6"
NEON_PURPLE = "#D500F9"
NEON_CYAN = "#18FFFF"
DARK_BG = "#0A0E17"
DARK_SURFACE = "#111827"
DARK_BORDER = "#1E293B"
DARK_GRID = "#1E293B"
MUTED = "#64748B"
TEXT_PRIMARY = "#E2E8F0"

# Legacy aliases used in chart code
BLUE = NEON_BLUE
RED = NEON_RED
ORANGE = NEON_ORANGE
AMBER = NEON_AMBER
GRAY = MUTED
LIGHT_GRAY = DARK_GRID
TEAL = NEON_TEAL
PURPLE = NEON_PURPLE
GREEN = NEON_GREEN

SIGNAL_COLORS = {
    "BUY": NEON_GREEN,
    "SELL": NEON_RED,
    "LONG": NEON_TEAL,
    "SHORT": NEON_ORANGE,
    "REDUCE": NEON_AMBER,
    "WATCH": NEON_CYAN,
}

LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    font=dict(family="'JetBrains Mono', 'SF Mono', 'Fira Code', monospace", size=11, color=TEXT_PRIMARY),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(10,14,23,0.6)",
    hoverlabel=dict(
        bgcolor="#1E293B",
        bordercolor="#334155",
        font=dict(family="'JetBrains Mono', monospace", size=12, color=TEXT_PRIMARY),
    ),
)


def _fig_to_json(fig) -> str:
    """Serialize a Plotly figure to JSON with plain arrays (no bdata)."""
    class _Encoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            if hasattr(obj, "item"):
                return obj.item()
            return super().default(obj)
    return json.dumps(fig.to_plotly_json(), cls=_Encoder)


def ticker_chart(df_ticker: pd.DataFrame, ticker: str, signals: list[dict] | None = None) -> str:
    """Price line with signal markers drawn directly on the line, score bars below."""
    df = df_ticker.sort_values("Date").copy()
    display_name = ticker_display(ticker)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # --- Price line ---
    fig.add_trace(
        go.Scatter(
            x=df["Date"].tolist(), y=df["Close"].tolist(),
            mode="lines", name="Price",
            line=dict(color=NEON_GREEN, width=2),
            hovertemplate="%{x|%b %d, %Y}<br><b>$%{y:,.2f}</b><extra></extra>",
        ),
        row=1, col=1,
    )

    # --- EWMA trend line ---
    if "ewma_value" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"].tolist(), y=df["ewma_value"].tolist(),
                mode="lines", name="Trend (EWMA)",
                line=dict(color=NEON_BLUE, width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>Trend: $%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # --- Signal markers ON the price line ---
    if signals and "consensus_anomaly" in df.columns:
        sig_lookup = {}
        for s in signals:
            if s["ticker"] == ticker:
                sig_lookup[s["date"]] = s["signal"]

        anomalies = df[df["consensus_anomaly"] == True].copy()
        if not anomalies.empty:
            date_strs = anomalies["Date"].apply(
                lambda d: d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
            )
            anomalies = anomalies.assign(signal_type=date_strs.map(sig_lookup).fillna("WATCH"))

            for sig_type, color in SIGNAL_COLORS.items():
                subset = anomalies[anomalies["signal_type"] == sig_type]
                if subset.empty:
                    continue
                label = sig_type.capitalize()
                fig.add_trace(
                    go.Scatter(
                        x=subset["Date"].tolist(), y=subset["Close"].tolist(),
                        mode="markers",
                        name=label,
                        marker=dict(
                            color=color,
                            size=11 if sig_type in ("BUY", "SELL", "SHORT", "LONG") else 8,
                            symbol="circle",
                            line=dict(width=2, color=DARK_BG),
                        ),
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "%{x|%b %d, %Y}<br>"
                            "$%{y:,.2f}<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )
    elif "consensus_anomaly" in df.columns:
        anomalies = df[df["consensus_anomaly"] == True]
        if not anomalies.empty:
            fig.add_trace(
                go.Scatter(
                    x=anomalies["Date"].tolist(), y=anomalies["Close"].tolist(),
                    mode="markers", name="Anomaly",
                    marker=dict(color=NEON_RED, size=9, symbol="circle",
                                line=dict(width=2, color=DARK_BG)),
                ),
                row=1, col=1,
            )

    # --- Consensus score bars (bottom panel) ---
    if "consensus_score" in df.columns:
        scores = df["consensus_score"].tolist()
        fig.add_trace(
            go.Bar(
                x=df["Date"].tolist(),
                y=scores,
                name="Anomaly Score",
                marker_color=[
                    NEON_RED if s > 0.6 else NEON_ORANGE if s > 0.4 else NEON_AMBER if s > 0.2 else DARK_BORDER
                    for s in scores
                ],
                hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.3f}<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.update_layout(
        title=dict(text=display_name, font_size=14, x=0.01, font_color=TEXT_PRIMARY),
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=10),
        margin=dict(l=55, r=20, t=45, b=30),
        hovermode="x unified",
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(title_text="Price ($)", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=2, col=1)

    return _fig_to_json(fig)


# ---- Per-method detail charts ----

def method_fourier_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Fourier score over time."""
    df = df_ticker.sort_values("Date").copy()
    if "fourier_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["fourier_score"].tolist(),
        mode="lines", name="Fourier Score",
        line=dict(color=NEON_PURPLE, width=1.5),
        fill="tozeroy", fillcolor="rgba(213,0,249,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    if "fourier_anomaly" in df.columns:
        anom = df[df["fourier_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["fourier_score"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=NEON_RED, size=7, line=dict(width=1, color=DARK_BG)),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Spectral Divergence",
        title=dict(text="Has the rhythm changed?", font_size=12, font_color=TEXT_PRIMARY),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    return _fig_to_json(fig)


def method_mp_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Matrix Profile score over time."""
    df = df_ticker.sort_values("Date").copy()
    if "mp_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["mp_score"].tolist(),
        mode="lines", name="Matrix Profile Score",
        line=dict(color=NEON_TEAL, width=1.5),
        fill="tozeroy", fillcolor="rgba(29,233,182,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    if "mp_anomaly" in df.columns:
        anom = df[df["mp_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["mp_score"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=NEON_RED, size=7, line=dict(width=1, color=DARK_BG)),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Nearest-Neighbor Distance",
        title=dict(text="Never-before-seen pattern?", font_size=12, font_color=TEXT_PRIMARY),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    return _fig_to_json(fig)


def method_ensemble_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Ensemble score with component breakdown."""
    df = df_ticker.sort_values("Date").copy()
    if "ensemble_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    for col, name, color in [
        ("zscore_component", "Z-Score", NEON_RED),
        ("seasonal_component", "Seasonal", NEON_ORANGE),
        ("iforest_component", "Isolation Forest", NEON_BLUE),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["Date"].tolist(), y=df[col].tolist(),
                mode="lines", name=name,
                line=dict(width=1, color=color),
                stackgroup="one",
                hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
            ))
    if "ensemble_anomaly" in df.columns:
        anom = df[df["ensemble_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["ensemble_score"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=NEON_RED, size=7, symbol="circle",
                            line=dict(width=1, color=DARK_BG)),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Component Score",
        title=dict(text="Do independent tests agree?", font_size=12, font_color=TEXT_PRIMARY),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=10),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    return _fig_to_json(fig)


def method_ewma_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """EWMA deviation chart."""
    df = df_ticker.sort_values("Date").copy()
    if "deviation_pct" not in df.columns:
        return "{}"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.08, row_heights=[0.55, 0.45])

    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["Close"].tolist(), mode="lines", name="Price",
        line=dict(color=NEON_GREEN, width=1.5),
        hovertemplate="$%{y:,.2f}<extra></extra>",
    ), row=1, col=1)
    if "ewma_value" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"].tolist(), y=df["ewma_value"].tolist(), mode="lines", name="EWMA",
            line=dict(color=NEON_BLUE, width=1.5, dash="dot"),
            hovertemplate="$%{y:,.2f}<extra></extra>",
        ), row=1, col=1)

    devs = df["deviation_pct"].tolist()
    colors = [NEON_RED if d < -3 else NEON_ORANGE if d < 0 else NEON_TEAL if d > 3 else DARK_BORDER
              for d in devs]
    fig.add_trace(go.Bar(
        x=df["Date"].tolist(), y=devs, name="Deviation %",
        marker_color=colors,
        hovertemplate="%{x|%b %d, %Y}<br>%{y:+.1f}% from trend<extra></extra>",
    ), row=2, col=1)

    if "ewma_anomaly" in df.columns:
        anom = df[df["ewma_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["Close"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=NEON_RED, size=7, line=dict(width=1, color=DARK_BG)),
            ), row=1, col=1)

    fig.update_layout(
        height=300, margin=dict(l=50, r=20, t=30, b=30),
        title=dict(text="Is momentum abnormal?", font_size=12, font_color=TEXT_PRIMARY),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_yaxes(title_text="Price ($)", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=1, col=1)
    fig.update_yaxes(title_text="Deviation %", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=2, col=1)
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    return _fig_to_json(fig)


# ---- Summary charts ----

def scoreboard_chart(results: pd.DataFrame) -> str:
    """Horizontal bar chart: latest consensus score per ticker, sorted by score."""
    latest = results.sort_values("Date").groupby("Ticker").tail(5)
    avg_recent = latest.groupby("Ticker")["consensus_score"].mean().sort_values(ascending=True)

    labels = [ticker_display(t) for t in avg_recent.index]
    scores = avg_recent.values.tolist()

    colors = [
        NEON_RED if s > 0.5 else NEON_ORANGE if s > 0.35 else NEON_AMBER if s > 0.2 else DARK_BORDER
        for s in scores
    ]

    fig = go.Figure(
        go.Bar(
            x=scores, y=labels, orientation="h", marker_color=colors,
            hovertemplate="<b>%{y}</b><br>Score: %{x:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, len(avg_recent) * 36 + 80),
        xaxis_title="Anomaly Score (recent 5-day avg)",
        margin=dict(l=140, r=20, t=20, b=40),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER, range=[0, max(max(scores) * 1.1, 0.1)])
    return _fig_to_json(fig)


# ---- Attention Queue heatmap ----

def attention_heatmap_chart(results: pd.DataFrame, alerts: list[dict] | None = None) -> str:
    """Create a heatmap: tickers (y) x last 14 trading days (x), colored by consensus score.

    Hover shows anomaly methods that fired and any trading signal for that cell.
    """
    if results.empty or "consensus_score" not in results.columns:
        return "{}"

    # Build signal lookup: (ticker, date_str) -> signal info
    sig_lookup: dict[tuple[str, str], dict] = {}
    if alerts:
        for a in alerts:
            key = (a["ticker"], a["date"])
            sig_lookup[key] = a

    # Method columns for hover detail
    method_cols = [
        ("fourier_anomaly", "Fourier"),
        ("mp_anomaly", "Matrix Profile"),
        ("ensemble_anomaly", "Ensemble"),
        ("ewma_anomaly", "EWMA"),
    ]

    # Get last 14 unique dates
    all_dates = sorted(results["Date"].unique())
    last_14 = all_dates[-14:] if len(all_dates) >= 14 else all_dates
    tickers = sorted(results["Ticker"].unique())

    # Build the matrix
    z_data = []
    hover_text = []
    for ticker in tickers:
        grp = results[results["Ticker"] == ticker].set_index("Date")
        row = []
        hrow = []
        for d in last_14:
            if d in grp.index:
                rec = grp.loc[d] if not isinstance(grp.loc[d], pd.DataFrame) else grp.loc[d].iloc[0]
                score = float(rec["consensus_score"])
                row.append(score)
                d_str = d.strftime("%b %d") if hasattr(d, "strftime") else str(d)[:10]
                d_iso = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]

                # Which methods flagged?
                fired = []
                for col, label in method_cols:
                    if col in results.columns:
                        val = rec[col] if not isinstance(rec, pd.DataFrame) else rec[col].iloc[0]
                        if val:
                            fired.append(label)
                methods_str = ", ".join(fired) if fired else "None"

                # Signal for this cell?
                sig = sig_lookup.get((ticker, d_iso))
                sig_str = f"<br><b>Signal: {sig['signal_label']}</b>" if sig else ""

                hover_line = (
                    f"<b>{ticker_display(ticker)}</b><br>"
                    f"{d_str} | Score: {score:.3f}<br>"
                    f"Methods: {methods_str}{sig_str}"
                )
                hrow.append(hover_line)
            else:
                row.append(0)
                hrow.append(f"{ticker_display(ticker)}<br>No data")
        z_data.append(row)
        hover_text.append(hrow)

    date_labels = [d.strftime("%b %d") if hasattr(d, "strftime") else str(d)[:10] for d in last_14]
    ticker_labels = [ticker_display(t) for t in tickers]

    fig = go.Figure(go.Heatmap(
        z=z_data,
        x=date_labels,
        y=ticker_labels,
        colorscale=[
            [0, DARK_SURFACE],
            [0.2, "#1a2332"],
            [0.4, "#1a3a2e"],
            [0.6, "#3a2a1a"],
            [0.8, "#4a1a1a"],
            [1.0, NEON_RED],
        ],
        hovertext=hover_text,
        hovertemplate="%{hovertext}<extra></extra>",
        showscale=True,
        colorbar=dict(
            title=dict(text="Score", font=dict(size=10, color=MUTED)),
            tickfont=dict(size=9, color=MUTED), len=0.6,
        ),
    ))

    fig.update_layout(
        height=max(400, len(tickers) * 28 + 100),
        margin=dict(l=180, r=40, t=20, b=40),
        xaxis=dict(side="top", tickfont=dict(size=9)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)

    return _fig_to_json(fig)


# ---- Attention Queue data (for table) ----

def compute_attention_queue(results: pd.DataFrame, alerts: list[dict]) -> list[dict]:
    """Compute attention-ranked list of tickers."""
    if results.empty:
        return []

    today = results["Date"].max()
    queue = []

    sig_lookup = {}
    for a in alerts:
        key = a["ticker"]
        if key not in sig_lookup or a["date"] > sig_lookup[key]["date"]:
            sig_lookup[key] = a

    for ticker, grp in results.groupby("Ticker"):
        g = grp.sort_values("Date")
        anomalies = g[g.get("consensus_anomaly", False) == True]

        if not anomalies.empty:
            last_anomaly_date = anomalies["Date"].max()
            days_since = (today - last_anomaly_date).days
        else:
            last_anomaly_date = None
            days_since = 999

        recent = g[g["Date"] >= today - pd.Timedelta(days=14)]
        max_severity = float(recent["consensus_score"].max()) if not recent.empty else 0

        streak = 0
        if "consensus_anomaly" in g.columns:
            for val in reversed(g["consensus_anomaly"].tolist()):
                if val:
                    streak += 1
                else:
                    break

        sig = sig_lookup.get(ticker)
        signal_type = sig["signal"] if sig else None
        signal_weight = 0
        if signal_type in ("BUY", "SELL", "LONG", "SHORT"):
            signal_weight = 1.0
        elif signal_type in ("REDUCE",):
            signal_weight = 0.7
        elif signal_type in ("WATCH",):
            signal_weight = 0.3

        recency_score = max(0, 1 - days_since / 30) * 30
        severity_score_pts = min(max_severity * 40, 40)
        persistence_score = min(streak * 5, 15)
        signal_score = signal_weight * 15
        attention_score = recency_score + severity_score_pts + persistence_score + signal_score

        last_30 = g.tail(30)
        sparkline = last_30["consensus_score"].tolist() if "consensus_score" in g.columns else []

        reg = TICKER_REGISTRY.get(ticker, {})
        category = reg.get("category", "")

        if len(g) >= 2 and "consensus_score" in g.columns:
            latest_score = float(g["consensus_score"].iloc[-1])
            prev_score = float(g["consensus_score"].iloc[-2])
            change = latest_score - prev_score
        else:
            latest_score = max_severity
            change = 0

        queue.append({
            "rank": 0,
            "ticker": ticker,
            "display": ticker_display(ticker),
            "category": category,
            "latest_severity": round(max_severity, 3),
            "change": round(change, 3),
            "days_since_anomaly": days_since if days_since < 999 else None,
            "last_anomaly_date": last_anomaly_date.strftime("%Y-%m-%d") if last_anomaly_date is not None and hasattr(last_anomaly_date, "strftime") else None,
            "streak": streak,
            "signal": signal_type,
            "signal_label": sig["signal_label"] if sig else None,
            "signal_color": sig["signal_color"] if sig else None,
            "attention_score": round(attention_score, 1),
            "sparkline": sparkline,
        })

    queue.sort(key=lambda x: x["attention_score"], reverse=True)
    for i, item in enumerate(queue):
        item["rank"] = i + 1

    return queue


# ---- Backtest: full lookback signal-following performance ----

def compute_backtest(results: pd.DataFrame, alerts: list[dict]) -> dict:
    """Compute signal performance — each signal = one $10k position.

    Model:
      - BUY/LONG: buy $10k at action price. Gain if price rose since.
      - SELL/SHORT before any buy: assume portfolio held $10k of that stock,
        sold at action price. Gain if price dropped since (good call).
      - Paired BUY→SELL: realized gain = (sell_price - buy_price) / buy_price.
      - Every position is a flat $10k unit.
    """
    empty = {
        "signal_ledger": [],
        "total_gain": 0,
        "total_pct": 0,
        "n_positions": 0,
        "n_winning": 0,
        "n_open": 0,
        "start_date": None,
        "end_date": None,
    }
    if results.empty or not alerts:
        return empty

    today = results["Date"].max()
    start = results["Date"].min()
    start_str = start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start)[:10]
    recent_alerts = [a for a in alerts if a["date"] >= start_str]

    if not recent_alerts:
        empty["start_date"] = str(start)[:10]
        empty["end_date"] = str(today)[:10]
        return empty

    # Latest price for each ticker
    latest_prices = {}
    for ticker in results["Ticker"].unique():
        grp = results[results["Ticker"] == ticker].sort_values("Date")
        if not grp.empty:
            latest_prices[ticker] = float(grp["Close"].iloc[-1])

    # Group by ticker, sort by date
    sig_timeline: dict[str, list] = {}
    for a in recent_alerts:
        sig_timeline.setdefault(a["ticker"], []).append(a)
    for t in sig_timeline:
        sig_timeline[t].sort(key=lambda x: x["date"])

    UNIT = 10_000
    signal_ledger = []

    for ticker, ticker_alerts in sig_timeline.items():
        current_price = latest_prices.get(ticker, 0)
        pending_buy = None

        for a in ticker_alerts:
            sig = a["signal"]
            price = a["close"]
            if price <= 0:
                continue

            if sig in ("BUY", "LONG"):
                if pending_buy:
                    # Close any existing open buy first (shouldn't happen often)
                    signal_ledger.append(pending_buy)
                # Open a $10k long position
                pct = (current_price - price) / price * 100 if current_price > 0 else 0
                gain = UNIT * pct / 100
                pending_buy = {
                    "date": a["date"],
                    "ticker": ticker,
                    "display": ticker_display(ticker),
                    "action": sig,
                    "action_price": round(price, 2),
                    "current_price": round(current_price, 2),
                    "pct_change": round(pct, 2),
                    "dollar_gain": round(gain, 2),
                    "status": "OPEN",
                }

            elif sig in ("SELL", "SHORT"):
                if pending_buy:
                    # Close the open buy → realized
                    pct = (price - pending_buy["action_price"]) / pending_buy["action_price"] * 100
                    gain = UNIT * pct / 100
                    pending_buy["current_price"] = round(price, 2)
                    pending_buy["pct_change"] = round(pct, 2)
                    pending_buy["dollar_gain"] = round(gain, 2)
                    pending_buy["status"] = "CLOSED"
                    signal_ledger.append(pending_buy)
                    pending_buy = None
                else:
                    # Standalone sell — assume held $10k, sold at this price.
                    # Good call if price dropped after selling.
                    pct = (price - current_price) / price * 100 if current_price > 0 else 0
                    gain = UNIT * pct / 100
                    signal_ledger.append({
                        "date": a["date"],
                        "ticker": ticker,
                        "display": ticker_display(ticker),
                        "action": sig,
                        "action_price": round(price, 2),
                        "current_price": round(current_price, 2),
                        "pct_change": round(pct, 2),
                        "dollar_gain": round(gain, 2),
                        "status": "OPEN",
                    })

            # Skip WATCH, REDUCE — not actionable positions

        if pending_buy:
            signal_ledger.append(pending_buy)

    # Sort by date descending
    signal_ledger.sort(key=lambda x: x["date"], reverse=True)

    # Summary stats
    total_gain = sum(s["dollar_gain"] for s in signal_ledger)
    n_positions = len(signal_ledger)
    n_winning = sum(1 for s in signal_ledger if s["dollar_gain"] > 0)
    n_open = sum(1 for s in signal_ledger if s["status"] == "OPEN")
    total_invested = n_positions * UNIT
    total_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0

    return {
        "signal_ledger": signal_ledger,
        "total_gain": round(total_gain, 2),
        "total_pct": round(total_pct, 2),
        "n_positions": n_positions,
        "n_winning": n_winning,
        "n_open": n_open,
        "start_date": str(start)[:10],
        "end_date": str(today)[:10],
    }


def backtest_equity_chart(backtest: dict) -> str:
    """Bar chart showing $ gain/loss per position ($10k each)."""
    ledger = backtest.get("signal_ledger", [])
    if not ledger:
        return "{}"

    # Sort by date ascending for the chart
    entries = sorted(ledger, key=lambda x: x["date"])

    labels = [f"{e['ticker']} {e['action']}<br>{e['date']}" for e in entries]
    gains = [e["dollar_gain"] for e in entries]
    colors = [NEON_GREEN if g >= 0 else NEON_RED for g in gains]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(entries))),
        y=gains,
        marker_color=colors,
        hovertext=[
            f"{e['ticker']} — {e['action']}<br>"
            f"Date: {e['date']}<br>"
            f"Entry: ${e['action_price']:,.2f}<br>"
            f"Current: ${e['current_price']:,.2f}<br>"
            f"Gain: ${e['dollar_gain']:+,.2f} ({e['pct_change']:+.1f}%)<br>"
            f"Status: {e['status']}"
            for e in entries
        ],
        hoverinfo="text",
        text=[f"${g:+,.0f}" for g in gains],
        textposition="outside",
        textfont=dict(size=9, color=TEXT_PRIMARY),
    ))

    fig.add_hline(y=0, line_color=MUTED, line_width=1)

    fig.update_layout(
        height=300,
        margin=dict(l=60, r=20, t=35, b=60),
        yaxis_title="$ Gain / Loss per $10k Position",
        title=dict(text="Position Performance — $10k per Signal", font_size=13, font_color=TEXT_PRIMARY),
        showlegend=False,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(len(entries))),
            ticktext=[f"{e['ticker']}" for e in entries],
            tickangle=-45,
            tickfont=dict(size=9),
        ),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    return _fig_to_json(fig)
