"""Chart generation — creates Plotly figures for the dashboard."""

import json
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# Color scheme
COLORS = {
    "price": "#2962FF",
    "ewma": "#FF6D00",
    "anomaly_critical": "#D50000",
    "anomaly_high": "#FF6D00",
    "anomaly_moderate": "#FFD600",
    "anomaly_low": "#2979FF",
    "volume": "rgba(41, 98, 255, 0.3)",
    "band_fill": "rgba(41, 98, 255, 0.08)",
    "grid": "#E0E0E0",
    "bg": "#FAFAFA",
}

SEVERITY_COLORS = {
    "CRITICAL": COLORS["anomaly_critical"],
    "HIGH": COLORS["anomaly_high"],
    "MODERATE": COLORS["anomaly_moderate"],
    "LOW": COLORS["anomaly_low"],
}


def ticker_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Generate an interactive price + anomaly chart for one ticker.

    Returns the Plotly figure as a JSON string for embedding.
    """
    df = df_ticker.sort_values("Date").copy()

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=[
            f"{ticker} — Price & Anomalies",
            "Detection Scores",
            "Volume",
        ],
    )

    # --- Row 1: Price line + EWMA + anomaly markers ---
    fig.add_trace(
        go.Scatter(
            x=df["Date"], y=df["Close"],
            mode="lines", name="Close",
            line=dict(color=COLORS["price"], width=1.5),
            hovertemplate="%{x|%b %d, %Y}<br>Close: $%{y:,.2f}<extra></extra>",
        ),
        row=1, col=1,
    )

    if "ewma_value" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"], y=df["ewma_value"],
                mode="lines", name="EWMA",
                line=dict(color=COLORS["ewma"], width=1, dash="dash"),
                hovertemplate="%{x|%b %d, %Y}<br>EWMA: $%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # Anomaly markers by severity
    anomalies = df[df["consensus_anomaly"] == True].copy()
    if not anomalies.empty:
        for severity, color in SEVERITY_COLORS.items():
            sev_mask = anomalies["methods_flagged"] >= {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}[severity]
            sev_max = anomalies["methods_flagged"] <= {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}[severity]
            subset = anomalies[sev_mask & sev_max]
            if subset.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=subset["Date"], y=subset["Close"],
                    mode="markers", name=f"{severity}",
                    marker=dict(color=color, size=8, symbol="diamond",
                                line=dict(width=1, color="white")),
                    hovertemplate=(
                        f"<b>{severity}</b><br>"
                        "%{x|%b %d, %Y}<br>"
                        "Close: $%{y:,.2f}<br>"
                        "<extra></extra>"
                    ),
                ),
                row=1, col=1,
            )

    # --- Row 2: Detection scores ---
    score_cols = {
        "fourier_score": ("Fourier", "#7C4DFF"),
        "mp_score": ("Matrix Profile", "#00BFA5"),
        "ensemble_score": ("Ensemble", "#FF6D00"),
        "ewma_score": ("EWMA", "#D50000"),
    }
    for col, (name, color) in score_cols.items():
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["Date"], y=df[col],
                    mode="lines", name=name,
                    line=dict(color=color, width=1),
                    hovertemplate=f"{name}: %{{y:.4f}}<extra></extra>",
                ),
                row=2, col=1,
            )

    # --- Row 3: Volume ---
    if "Volume" in df.columns:
        fig.add_trace(
            go.Bar(
                x=df["Date"], y=df["Volume"],
                name="Volume",
                marker_color=COLORS["volume"],
                hovertemplate="%{x|%b %d, %Y}<br>Volume: %{y:,.0f}<extra></extra>",
            ),
            row=3, col=1,
        )

    fig.update_layout(
        height=700,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=30, t=60, b=40),
        hovermode="x unified",
        font=dict(family="Inter, -apple-system, sans-serif", size=12),
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], row=1, col=1)
    fig.update_yaxes(title_text="Price ($)", gridcolor=COLORS["grid"], row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=COLORS["grid"], row=2, col=1)
    fig.update_yaxes(title_text="Volume", gridcolor=COLORS["grid"], row=3, col=1)

    return fig.to_json()


def summary_heatmap(results: pd.DataFrame) -> str:
    """Generate a heatmap of consensus scores across tickers and recent dates.

    Returns a Plotly figure as a JSON string.
    """
    # Get last 30 trading days
    recent = results.sort_values("Date").groupby("Ticker").tail(30)
    pivot = recent.pivot_table(
        index="Ticker", columns="Date", values="consensus_score", aggfunc="first"
    )
    pivot = pivot.fillna(0)

    # Format dates for display
    date_labels = [d.strftime("%b %d") if hasattr(d, "strftime") else str(d) for d in pivot.columns]

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=date_labels,
            y=pivot.index.tolist(),
            colorscale=[
                [0, "#F5F5F5"],
                [0.5, "#FFE082"],
                [0.75, "#FF8A65"],
                [1.0, "#D50000"],
            ],
            hovertemplate="Ticker: %{y}<br>Date: %{x}<br>Score: %{z:.4f}<extra></extra>",
            colorbar=dict(title="Score"),
        )
    )
    fig.update_layout(
        title="Anomaly Score Heatmap (Last 30 Trading Days)",
        height=max(400, len(pivot) * 25 + 100),
        template="plotly_white",
        font=dict(family="Inter, -apple-system, sans-serif", size=12),
        margin=dict(l=80, r=30, t=60, b=60),
    )
    return fig.to_json()


def alert_distribution_chart(alerts: list[dict]) -> str:
    """Pie chart of alert severity distribution."""
    if not alerts:
        return "{}"

    severity_counts = {}
    for a in alerts:
        s = a["severity"]
        severity_counts[s] = severity_counts.get(s, 0) + 1

    labels = list(severity_counts.keys())
    values = list(severity_counts.values())
    colors = [SEVERITY_COLORS.get(l, "#999") for l in labels]

    fig = go.Figure(
        data=[go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            hole=0.4,
            hovertemplate="%{label}: %{value} alerts<extra></extra>",
        )]
    )
    fig.update_layout(
        title="Alert Severity Distribution",
        height=350,
        template="plotly_white",
        font=dict(family="Inter, -apple-system, sans-serif", size=12),
        margin=dict(l=30, r=30, t=60, b=30),
    )
    return fig.to_json()
