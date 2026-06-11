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


# ---- Backtest chart (computation lives in anomaly_detection.backtest) ----


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
            name="Strategy",
            hovertemplate="%{x}<br>$%{y:+,.0f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Benchmark overlay: the identical capital left 100% in the baseline —
    # the exact "what if you'd done nothing" portfolio.
    bench = backtest.get("benchmark") or {}
    if bench.get("dates"):
        fig.add_trace(
            go.Scatter(
                x=bench["dates"], y=bench["equity"],
                mode="lines",
                line=dict(color=MUTED, width=1.5, dash="dash"),
                name=f"{bench.get('ticker', 'SPY')} baseline (no signals)",
                hovertemplate="%{x}<br>$%{y:+,.0f}<extra></extra>",
            ),
            row=1, col=1,
        )
    fig.add_hline(y=0, line_color=MUTED, line_width=1, row=1, col=1)

    # Overlay invest markers on the equity curve (the book only ever invests;
    # divests are implicit in each trade's exit).
    marks = {"x": [], "y": [], "txt": [], "color": []}
    date_to_equity = dict(zip(dates, equity))
    for t in ledger:
        d = t.get("entry_date")
        if d not in date_to_equity:
            continue
        marks["x"].append(d)
        marks["y"].append(date_to_equity[d])
        marks["color"].append(SIGNAL_COLORS.get(t.get("action", "BUY"), NEON_GREEN))
        marks["txt"].append(
            f"{t['ticker']} {t['action']} (invest ${t.get('unit', 0):,.0f})<br>"
            f"Entry ${t['entry_price']:,.2f}<br>"
            f"Status: {t['status']}<br>"
            f"P&L: ${t['dollar_gain']:+,.2f}"
        )

    if marks["x"]:
        fig.add_trace(go.Scatter(
            x=marks["x"], y=marks["y"],
            mode="markers", marker=dict(symbol="triangle-up", size=9,
                                        color=marks["color"],
                                        line=dict(color=DARK_BG, width=1)),
            name="Invest",
            text=marks["txt"], hoverinfo="text",
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
