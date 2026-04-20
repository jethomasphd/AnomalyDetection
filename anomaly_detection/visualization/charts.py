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

def compute_backtest(
    results: pd.DataFrame,
    alerts: list[dict],
    unit: float = 10_000,
) -> dict:
    """Simulate signal performance from the anchored start date forward.

    Trade model:
      - Every actionable signal (BUY/LONG/SELL/SHORT) opens a new $10k trade
        at the close of the signal's bar date. Long for BUY/LONG, short for
        SELL/SHORT. WATCH and REDUCE are informational only.
      - Multiple same-direction signals on a ticker stack into independent
        positions (three BUYs on AAPL = three independent $10k longs).
      - An opposite-direction signal on a ticker closes EVERY open position
        of the other direction at that day's close, realising their P&L,
        and then opens its own new position.
      - No baseline, no buy-and-hold reference — only trades the Signal
        actually produced.

    Every open trade is marked-to-current at the last available bar. The
    equity curve is a daily mark-to-market time series (realised P&L on
    closed trades + unrealised P&L on still-open trades, per ticker,
    summed each day), which is what powers Sharpe / drawdown downstream.
    """
    empty = {
        "signal_ledger": [],
        "total_gain": 0.0,
        "realized_gain": 0.0,
        "unrealized_gain": 0.0,
        "total_invested": 0.0,
        "n_trades": 0,
        "n_winning": 0,
        "n_open": 0,
        "n_closed": 0,
        "start_date": None,
        "end_date": None,
        "equity_curve": {"dates": [], "equity": [], "drawdown": []},
        "stats": _empty_trade_stats(),
    }
    if results.empty or not alerts:
        return empty

    # Per-ticker sorted price series (as float arrays keyed by DateStr)
    by_ticker = _build_price_index(results)
    all_dates = _union_sorted_dates(by_ticker)
    if not all_dates:
        return empty

    start_str = all_dates[0]
    today_str = all_dates[-1]

    # Long = +1, Short = -1
    def direction_for(sig: str) -> int | None:
        if sig in ("BUY", "LONG"):
            return +1
        if sig in ("SELL", "SHORT"):
            return -1
        return None

    # ----- Simulate trades chronologically -----
    # open_trades[ticker] is a list of open trade dicts.
    open_trades: dict[str, list[dict]] = {}
    closed_trades: list[dict] = []
    trade_seq = 0  # stable ordering for display

    # Sort alerts by (date, ticker, signal) so ties are deterministic.
    tradable = [
        a for a in alerts
        if direction_for(a.get("signal")) is not None
        and a.get("date", "") >= start_str
    ]
    tradable.sort(key=lambda a: (a["date"], a["ticker"], a["signal"]))

    for a in tradable:
        sig = a["signal"]
        ticker = a["ticker"]
        series = by_ticker.get(ticker)
        if series is None:
            continue

        # Resolve the trade price from the ticker's own bar on or after
        # signal.date — if the signal's bar isn't in the frame (e.g. the
        # ticker was delisted), skip it.
        entry_price, entry_date_resolved = _price_on_or_after(series, a["date"])
        if entry_price is None or entry_price <= 0:
            continue

        new_dir = direction_for(sig)

        # Close any opposite-direction positions on this ticker at today's close
        still_open = []
        for t in open_trades.get(ticker, []):
            if t["direction"] != new_dir:
                pnl = _position_pnl(t, entry_price)
                closed_trades.append(_close_trade(
                    t, exit_date=entry_date_resolved, exit_price=entry_price,
                    exit_reason="opposite_signal", pnl=pnl, series=series,
                ))
            else:
                still_open.append(t)
        open_trades[ticker] = still_open

        # Open the new trade
        trade_seq += 1
        open_trades.setdefault(ticker, []).append({
            "id": trade_seq,
            "ticker": ticker,
            "direction": new_dir,
            "action": sig,
            "entry_date": entry_date_resolved,
            "entry_price": entry_price,
            "unit": unit,
            "confidence": a.get("confidence", ""),
            "methods": _methods_list(a),
            "methods_flagged": int(a.get("methods_flagged", 0)),
            "bar_date": a["date"],
        })

    # Mark remaining open trades to the latest available close
    still_open_flat: list[dict] = []
    for ticker, trades in open_trades.items():
        series = by_ticker.get(ticker)
        last_close = float(series["Close"][-1]) if series is not None and len(series["Close"]) else 0.0
        last_date = series["DateStr"][-1] if series is not None and len(series["DateStr"]) else today_str
        for t in trades:
            marked = _close_trade(
                t, exit_date=last_date, exit_price=last_close,
                exit_reason="open", pnl=_position_pnl(t, last_close), series=series,
            )
            marked["status"] = "OPEN"
            still_open_flat.append(marked)

    for t in closed_trades:
        t["status"] = "CLOSED"

    signal_ledger = sorted(
        closed_trades + still_open_flat,
        key=lambda t: (t["entry_date"], t["id"]),
        reverse=True,
    )

    # ----- Daily mark-to-market equity curve -----
    equity_curve = _build_equity_curve(closed_trades, still_open_flat, by_ticker, all_dates, unit=unit)

    # Summary
    realized_gain = sum(t["dollar_gain"] for t in closed_trades)
    unrealized_gain = sum(t["dollar_gain"] for t in still_open_flat)
    total_gain = realized_gain + unrealized_gain
    n_closed = len(closed_trades)
    n_open = len(still_open_flat)
    n_trades = n_closed + n_open
    n_winning = sum(1 for t in signal_ledger if t["dollar_gain"] > 0)
    total_invested = n_trades * unit

    stats = _compute_trade_stats(
        closed_trades=closed_trades,
        equity_curve=equity_curve,
        unit=unit,
        n_trades_total=n_trades,
    )

    return {
        "signal_ledger": signal_ledger,
        "total_gain": round(total_gain, 2),
        "total_pct": round((total_gain / total_invested * 100) if total_invested > 0 else 0, 2),
        "realized_gain": round(realized_gain, 2),
        "unrealized_gain": round(unrealized_gain, 2),
        "total_invested": total_invested,
        "n_trades": n_trades,
        "n_winning": n_winning,
        "n_open": n_open,
        "n_closed": n_closed,
        "start_date": start_str,
        "end_date": today_str,
        "equity_curve": equity_curve,
        "stats": stats,
    }


# ----- backtest helpers -----

def _build_price_index(results: pd.DataFrame) -> dict[str, dict]:
    """Pre-index prices per ticker as plain numpy arrays for fast lookup."""
    out: dict[str, dict] = {}
    for ticker, grp in results.groupby("Ticker"):
        g = grp[["Date", "Close"]].sort_values("Date").reset_index(drop=True)
        if g.empty:
            continue
        date_strs = pd.to_datetime(g["Date"]).dt.strftime("%Y-%m-%d").tolist()
        closes = g["Close"].to_numpy(dtype=float)
        out[ticker] = {
            "DateStr": date_strs,
            "Close": closes,
            # DateStr -> index, for O(1) lookup during MTM
            "_index": {d: i for i, d in enumerate(date_strs)},
        }
    return out


def _union_sorted_dates(by_ticker: dict[str, dict]) -> list[str]:
    s: set[str] = set()
    for v in by_ticker.values():
        s.update(v["DateStr"])
    return sorted(s)


def _price_on_or_after(series: dict, date_str: str) -> tuple[float | None, str | None]:
    """First bar at or after date_str (YYYY-MM-DD)."""
    dates = series["DateStr"]
    # Linear scan — trading series per ticker is small (a few hundred bars)
    for i, d in enumerate(dates):
        if d >= date_str:
            return float(series["Close"][i]), d
    return None, None


def _position_pnl(trade: dict, mark_price: float) -> float:
    """Signed $ P&L of a position marked at `mark_price`."""
    if trade["entry_price"] <= 0 or mark_price <= 0:
        return 0.0
    pct = (mark_price - trade["entry_price"]) / trade["entry_price"]
    return trade["direction"] * pct * trade["unit"]


def _close_trade(trade: dict, *, exit_date: str, exit_price: float,
                 exit_reason: str, pnl: float, series: dict | None) -> dict:
    """Return a ledger-row dict from an open trade + exit info."""
    pct = 0.0
    if trade["entry_price"] > 0:
        pct = trade["direction"] * (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
    held = 0
    if series is not None and exit_date:
        idx = series["_index"]
        i0 = idx.get(trade["entry_date"])
        i1 = idx.get(exit_date)
        if i0 is not None and i1 is not None:
            held = max(0, i1 - i0)
    return {
        "id": trade["id"],
        "date": trade["bar_date"],
        "ticker": trade["ticker"],
        "display": ticker_display(trade["ticker"]),
        "action": trade["action"],
        "direction": trade["direction"],
        "entry_date": trade["entry_date"],
        "exit_date": exit_date,
        "action_price": round(trade["entry_price"], 2),
        "entry_price": round(trade["entry_price"], 2),
        "exit_price": round(exit_price, 2),
        "current_price": round(exit_price, 2),
        "dollar_gain": round(pnl, 2),
        "pct_change": round(pct, 2),
        "exit_reason": exit_reason,
        "holding_days": held,
        "methods": trade.get("methods", ""),
        "methods_flagged": trade.get("methods_flagged", 0),
        "confidence": trade.get("confidence", ""),
        # Preserved for the equity-curve walker; round for clean JSON.
        "unit": round(trade["unit"], 2),
        "_entry_price_raw": trade["entry_price"],
    }


def _build_equity_curve(
    closed_trades: list[dict],
    open_trades_marked: list[dict],
    by_ticker: dict[str, dict],
    all_dates: list[str],
    unit: float,
) -> dict:
    """Build a daily mark-to-market equity series across every trading day.

    For each day d:
        equity(d) = sum over all trades whose entry_date <= d of:
            realized P&L if exit_date <= d
            mark-to-market P&L against close(d) if still open on d

    Returns {dates, equity, drawdown} as parallel lists. Drawdown is the
    running-max-minus-equity underwater curve in dollars.
    """
    if not all_dates:
        return {"dates": [], "equity": [], "drawdown": []}

    # Reconstruct "positions with exit info" for everyone.
    all_trades = []
    for t in closed_trades:
        all_trades.append({**t, "status": "CLOSED"})
    for t in open_trades_marked:
        all_trades.append({**t, "status": "OPEN", "exit_date_override": None})

    # Per-day equity
    equity = np.zeros(len(all_dates), dtype=float)
    for t in all_trades:
        ticker = t["ticker"]
        series = by_ticker.get(ticker)
        if series is None:
            continue
        entry_i = _date_index(all_dates, t["entry_date"])
        # For closed trades, the exit date is a real lock-in point.
        # For open trades, effective "lock-in" never happens; they keep marking.
        if t.get("status") == "CLOSED":
            exit_i = _date_index(all_dates, t["exit_date"])
        else:
            exit_i = None  # open: mark all the way to end

        if entry_i is None:
            continue

        # Walk day by day from entry to end; for CLOSED, after exit_i use the
        # realized P&L; for OPEN, mark against the ticker's close on each day.
        for i in range(entry_i, len(all_dates)):
            d = all_dates[i]
            if exit_i is not None and i >= exit_i:
                pnl = t["dollar_gain"]  # realized, locked in
            else:
                mark = _close_on(series, d)
                if mark is None:
                    # Ticker has no bar on this day (holiday skew, delisting) —
                    # carry the previous marked value forward.
                    prev = _last_close_on_or_before(series, d)
                    if prev is None:
                        continue
                    mark = prev
                entry_px = t.get("_entry_price_raw") or t["entry_price"]
                pnl = t["direction"] * (mark - entry_px) / entry_px * t["unit"] if entry_px > 0 else 0.0
            equity[i] += pnl

    # Drawdown in $
    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity  # always >= 0

    return {
        "dates": all_dates,
        "equity": [round(float(x), 2) for x in equity],
        "drawdown": [round(float(x), 2) for x in drawdown],
    }


def _date_index(all_dates: list[str], d: str | None) -> int | None:
    if d is None:
        return None
    # dates are sorted; use bisect for speed on larger series
    import bisect
    i = bisect.bisect_left(all_dates, d)
    if i < len(all_dates) and all_dates[i] == d:
        return i
    # Otherwise use the first date >= d (signal may have fallen on a market holiday)
    return i if i < len(all_dates) else None


def _close_on(series: dict, date_str: str) -> float | None:
    i = series["_index"].get(date_str)
    return float(series["Close"][i]) if i is not None else None


def _last_close_on_or_before(series: dict, date_str: str) -> float | None:
    """Return the most recent close at or before date_str (for carry-forward)."""
    import bisect
    i = bisect.bisect_right(series["DateStr"], date_str) - 1
    if i < 0:
        return None
    return float(series["Close"][i])


def _empty_trade_stats() -> dict:
    return {
        "sharpe": None, "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
        "win_rate": 0.0, "avg_hold_days": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": None,
        "hit_rate_by_signal": {}, "n_closed": 0,
    }


def _compute_trade_stats(
    closed_trades: list[dict],
    equity_curve: dict,
    unit: float = 10_000,
    n_trades_total: int | None = None,
) -> dict:
    """Risk & quality stats.

    - Sharpe & Max Drawdown come from the DAILY mark-to-market equity curve
      (realized + unrealized). This is the honest, time-series definition:
      it tells you what a manager's equity actually did, day by day, as the
      strategy ran. Computing these on closed trades alone would ignore the
      unrealized-but-volatile portion of the book.

    - Win rate, profit factor, avg holding period, and hit-rate-by-signal
      come from CLOSED trades only, because "win" is only meaningful once
      realized.
    """
    stats = _empty_trade_stats()
    n_closed = len(closed_trades)
    stats["n_closed"] = n_closed

    equity = np.array(equity_curve.get("equity", []), dtype=float)
    if equity.size >= 2:
        # Daily $ change in equity
        daily_pnl = np.diff(equity)
        # Denominator for a return: scale by the total capital deployed.
        # It's stable across time (it doesn't decline with drawdowns), which
        # matches how a dollar-based strategy is usually evaluated.
        deployed = max(unit, 1.0)  # at minimum one trade of capital
        # If multiple trades ran, deployed = number of trades * unit — but we
        # use the equity's own variability, not pct returns, for simplicity.
        # Sharpe on $ returns, annualised by sqrt(252).
        std_pnl = float(daily_pnl.std(ddof=1)) if daily_pnl.size > 1 else 0.0
        mean_pnl = float(daily_pnl.mean()) if daily_pnl.size else 0.0
        if std_pnl > 0:
            stats["sharpe"] = round((mean_pnl / std_pnl) * float(np.sqrt(252)), 2)

        # Drawdown in dollars; pct expressed against total capital deployed
        # (n_trades × unit) so a 10% reading means "the book was ever $1 of
        # every $10 committed underwater from its peak." This stays
        # interpretable even when the equity peak is small or near zero.
        drawdown = np.array(equity_curve.get("drawdown", []), dtype=float)
        if drawdown.size:
            max_dd = float(drawdown.max())
            stats["max_drawdown"] = round(max_dd, 2)
            capital = (n_trades_total or 1) * unit
            if capital > 0:
                stats["max_drawdown_pct"] = round(max_dd / capital * 100, 2)

    if n_closed:
        pnl = np.array([float(t["dollar_gain"]) for t in closed_trades])
        holds = np.array([int(t.get("holding_days") or 0) for t in closed_trades], dtype=float)
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        stats["win_rate"] = round(len(wins) / n_closed * 100, 1)
        stats["avg_hold_days"] = round(float(holds.mean()) if holds.size else 0.0, 1)
        stats["avg_win"] = round(float(wins.mean()), 2) if wins.size else 0.0
        stats["avg_loss"] = round(float(losses.mean()), 2) if losses.size else 0.0
        loss_sum = float(abs(losses.sum()))
        if loss_sum > 0:
            stats["profit_factor"] = round(float(wins.sum()) / loss_sum, 2)

        by_sig: dict[str, list[float]] = {}
        for t in closed_trades:
            by_sig.setdefault(t["action"], []).append(float(t["dollar_gain"]))
        hit: dict[str, dict] = {}
        for sig, vals in by_sig.items():
            arr = np.array(vals)
            n_sig = len(arr)
            n_win = int((arr > 0).sum())
            hit[sig] = {
                "n": n_sig,
                "n_win": n_win,
                "win_rate": (n_win / n_sig) if n_sig else 0.0,
                "avg_pnl": float(arr.mean()) if n_sig else 0.0,
            }
        stats["hit_rate_by_signal"] = hit
    return stats


def _methods_list(alert: dict) -> str:
    """Return a compact string of which detection methods flagged this alert."""
    details = alert.get("details", {})
    methods = []
    if details.get("fourier_score", 0) > 0:
        methods.append("Fourier")
    if details.get("mp_score", 0) > 0:
        methods.append("MatrixProfile")
    if details.get("ensemble_score", 0) > 0:
        methods.append("Ensemble")
    if details.get("ewma_score", 0) > 0:
        methods.append("EWMA")
    return ", ".join(methods) if methods else f"{alert.get('methods_flagged', '?')} methods"


def backtest_equity_chart(backtest: dict) -> str:
    """Two-row figure: daily mark-to-market equity + underwater drawdown.

    Top panel: cumulative $ P&L over time (realised + unrealised combined)
    with signal markers annotating BUY/LONG and SELL/SHORT entries.
    Bottom panel: underwater curve showing peak-to-trough drop at every point.
    """
    curve = backtest.get("equity_curve") or {}
    dates = curve.get("dates") or []
    equity = curve.get("equity") or []
    drawdown = curve.get("drawdown") or []
    if not dates or not equity:
        return "{}"

    ledger = backtest.get("signal_ledger", [])

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Cumulative $ P&L — daily mark-to-market",
                        "Drawdown (underwater)"),
    )

    # Equity curve — fill when positive/negative for a quick visual read.
    fig.add_trace(
        go.Scatter(
            x=dates, y=equity,
            mode="lines",
            line=dict(color=NEON_GREEN, width=2),
            fill="tozeroy",
            fillcolor="rgba(0,230,118,0.08)",
            name="Equity",
            hovertemplate="%{x}<br>$%{y:+,.0f}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_hline(y=0, line_color=MUTED, line_width=1, row=1, col=1)

    # Overlay buy/sell markers on the equity curve
    entry_marks = {"long": {"x": [], "y": [], "txt": []},
                   "short": {"x": [], "y": [], "txt": []}}
    date_to_equity = dict(zip(dates, equity))
    for t in ledger:
        d = t.get("entry_date")
        if d not in date_to_equity:
            continue
        eq = date_to_equity[d]
        grp = "long" if t["direction"] > 0 else "short"
        entry_marks[grp]["x"].append(d)
        entry_marks[grp]["y"].append(eq)
        entry_marks[grp]["txt"].append(
            f"{t['ticker']} {t['action']}<br>"
            f"Entry ${t['entry_price']:,.2f}<br>"
            f"Status: {t['status']}<br>"
            f"P&L: ${t['dollar_gain']:+,.2f}"
        )

    if entry_marks["long"]["x"]:
        fig.add_trace(go.Scatter(
            x=entry_marks["long"]["x"], y=entry_marks["long"]["y"],
            mode="markers", marker=dict(symbol="triangle-up", size=10,
                                        color=NEON_GREEN, line=dict(color=DARK_BG, width=1)),
            name="Long entry",
            text=entry_marks["long"]["txt"], hoverinfo="text",
        ), row=1, col=1)
    if entry_marks["short"]["x"]:
        fig.add_trace(go.Scatter(
            x=entry_marks["short"]["x"], y=entry_marks["short"]["y"],
            mode="markers", marker=dict(symbol="triangle-down", size=10,
                                        color=NEON_RED, line=dict(color=DARK_BG, width=1)),
            name="Short entry",
            text=entry_marks["short"]["txt"], hoverinfo="text",
        ), row=1, col=1)

    # Underwater curve (drawdown shown as negative values)
    dd_neg = [-x for x in drawdown]
    fig.add_trace(
        go.Scatter(
            x=dates, y=dd_neg,
            mode="lines",
            line=dict(color=NEON_RED, width=1.5),
            fill="tozeroy",
            fillcolor="rgba(255,23,68,0.12)",
            name="Drawdown",
            hovertemplate="%{x}<br>-$%{customdata:,.0f}<extra></extra>",
            customdata=drawdown,
        ),
        row=2, col=1,
    )

    fig.update_layout(
        height=440,
        margin=dict(l=60, r=20, t=50, b=40),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=DARK_GRID, linecolor=DARK_BORDER)
    fig.update_yaxes(title_text="$ P&L", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=1, col=1)
    fig.update_yaxes(title_text="Drawdown $", gridcolor=DARK_GRID, linecolor=DARK_BORDER, row=2, col=1)
    for ann in fig.layout.annotations:
        ann.font = dict(size=11, color=TEXT_PRIMARY)
    return _fig_to_json(fig)
