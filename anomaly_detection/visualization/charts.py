"""Chart generation — clean Plotly figures for the dashboard."""

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# --- Color palette ---
BLUE = "#2962FF"
RED = "#D50000"
ORANGE = "#FF6D00"
AMBER = "#F9A825"
GRAY = "#9E9E9E"
LIGHT_GRAY = "#E0E0E0"

SEVERITY_COLORS = {
    "CRITICAL": RED,
    "HIGH": ORANGE,
    "MODERATE": AMBER,
    "LOW": "#42A5F5",
}


def ticker_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Single clean chart: price line + EWMA + anomaly markers, with a score panel below."""
    df = df_ticker.sort_values("Date").copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # --- Price line ---
    fig.add_trace(
        go.Scatter(
            x=df["Date"], y=df["Close"],
            mode="lines", name="Price",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{x|%b %d, %Y}<br><b>$%{y:,.2f}</b><extra></extra>",
        ),
        row=1, col=1,
    )

    # --- EWMA trend line ---
    if "ewma_value" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"], y=df["ewma_value"],
                mode="lines", name="Trend (EWMA)",
                line=dict(color=ORANGE, width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>Trend: $%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # --- Anomaly markers (one trace per severity for legend) ---
    anomalies = df[df.get("consensus_anomaly", pd.Series(dtype=bool)) == True].copy()
    if not anomalies.empty:
        severity_ranges = [
            ("CRITICAL", lambda m: m >= 4),
            ("HIGH",     lambda m: m == 3),
            ("MODERATE", lambda m: m == 2),
            ("LOW",      lambda m: m <= 1),
        ]
        for sev_name, sev_fn in severity_ranges:
            mask = anomalies["methods_flagged"].apply(sev_fn)
            subset = anomalies[mask]
            if subset.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=subset["Date"], y=subset["Close"],
                    mode="markers",
                    name=sev_name,
                    marker=dict(
                        color=SEVERITY_COLORS[sev_name],
                        size=10 if sev_name in ("CRITICAL", "HIGH") else 8,
                        symbol="diamond",
                        line=dict(width=1.5, color="white"),
                    ),
                    hovertemplate=(
                        f"<b>{sev_name}</b><br>"
                        "%{x|%b %d, %Y}<br>"
                        "$%{y:,.2f}<extra></extra>"
                    ),
                ),
                row=1, col=1,
            )

    # --- Consensus score (bottom panel) ---
    if "consensus_score" in df.columns:
        fig.add_trace(
            go.Bar(
                x=df["Date"],
                y=df["consensus_score"],
                name="Anomaly Score",
                marker_color=[
                    RED if s > 0.6 else ORANGE if s > 0.4 else AMBER if s > 0.2 else LIGHT_GRAY
                    for s in df["consensus_score"]
                ],
                hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.3f}<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.update_layout(
        height=500,
        template="plotly_white",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        margin=dict(l=55, r=20, t=30, b=30),
        hovermode="x unified",
        font=dict(family="Inter, system-ui, sans-serif", size=12),
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(title_text="Price ($)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=LIGHT_GRAY, row=2, col=1)

    return fig.to_json()


def scoreboard_chart(results: pd.DataFrame) -> str:
    """Horizontal bar chart: latest consensus score per ticker, sorted by score.

    This is the hero chart — at a glance, which tickers need attention.
    """
    latest = results.sort_values("Date").groupby("Ticker").tail(5)
    avg_recent = latest.groupby("Ticker")["consensus_score"].mean().sort_values(ascending=True)

    colors = [
        RED if s > 0.5 else ORANGE if s > 0.35 else AMBER if s > 0.2 else "#90CAF9"
        for s in avg_recent.values
    ]

    fig = go.Figure(
        go.Bar(
            x=avg_recent.values,
            y=avg_recent.index.tolist(),
            orientation="h",
            marker_color=colors,
            hovertemplate="<b>%{y}</b><br>Score: %{x:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, len(avg_recent) * 32 + 80),
        template="plotly_white",
        xaxis_title="Anomaly Score (recent 5-day avg)",
        margin=dict(l=60, r=20, t=20, b=40),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY, range=[0, max(avg_recent.values.max() * 1.1, 0.1)])

    return fig.to_json()


def history_chart(history_data: list[dict]) -> str:
    """Line chart showing total anomaly count per run date."""
    if not history_data:
        return "{}"

    dates = [h["run_date"] for h in history_data]
    counts = [h["anomalies_detected"] for h in history_data]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates, y=counts,
            mode="lines+markers",
            name="Anomalies",
            line=dict(color=RED, width=2),
            marker=dict(size=6),
            hovertemplate="%{x}<br><b>%{y} anomalies</b><extra></extra>",
        )
    )
    fig.update_layout(
        height=250,
        template="plotly_white",
        margin=dict(l=50, r=20, t=20, b=30),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        yaxis_title="Anomalies Detected",
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)

    return fig.to_json()
