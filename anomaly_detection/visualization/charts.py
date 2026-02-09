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
TEAL = "#00897B"
PURPLE = "#7C4DFF"

SEVERITY_COLORS = {
    "CRITICAL": RED,
    "HIGH": ORANGE,
    "MODERATE": AMBER,
    "LOW": "#42A5F5",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
)


def ticker_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Price line with anomaly markers drawn directly on the line, score bars below."""
    df = df_ticker.sort_values("Date").copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # --- Price line (base) ---
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

    # --- Anomaly markers ON the price line ---
    # We re-draw just the anomaly points as a scatter with markers sitting
    # directly on top of the price line, so they appear embedded in it.
    if "consensus_anomaly" in df.columns:
        anomalies = df[df["consensus_anomaly"] == True].copy()
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
                            size=11 if sev_name in ("CRITICAL", "HIGH") else 9,
                            symbol="circle",
                            line=dict(width=2, color="white"),
                        ),
                        hovertemplate=(
                            f"<b>{sev_name}</b><br>"
                            "%{x|%b %d, %Y}<br>"
                            "$%{y:,.2f}<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )

    # --- Consensus score bars (bottom panel) ---
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
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        margin=dict(l=55, r=20, t=30, b=30),
        hovermode="x unified",
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(title_text="Price ($)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=LIGHT_GRAY, row=2, col=1)

    return fig.to_json()


# ---- Per-method detail charts ----

def method_fourier_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Fourier score over time with anomaly threshold region."""
    df = df_ticker.sort_values("Date").copy()
    if "fourier_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["fourier_score"],
        mode="lines", name="Fourier Score",
        line=dict(color=PURPLE, width=1.5),
        fill="tozeroy", fillcolor="rgba(124,77,255,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    # Highlight anomaly points on the line
    if "fourier_anomaly" in df.columns:
        anom = df[df["fourier_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"], y=anom["fourier_score"],
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Spectral Divergence",
        title=dict(text=f"{ticker} — Has the rhythm changed?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return fig.to_json()


def method_mp_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Matrix Profile score over time."""
    df = df_ticker.sort_values("Date").copy()
    if "mp_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["mp_score"],
        mode="lines", name="Matrix Profile Score",
        line=dict(color=TEAL, width=1.5),
        fill="tozeroy", fillcolor="rgba(0,137,123,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    if "mp_anomaly" in df.columns:
        anom = df[df["mp_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"], y=anom["mp_score"],
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Nearest-Neighbor Distance",
        title=dict(text=f"{ticker} — Never-before-seen pattern?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return fig.to_json()


def method_ensemble_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Ensemble score with component breakdown."""
    df = df_ticker.sort_values("Date").copy()
    if "ensemble_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    # Stacked area of the three components
    for col, name, color in [
        ("zscore_component", "Z-Score", "#EF5350"),
        ("seasonal_component", "Seasonal", "#FFA726"),
        ("iforest_component", "Isolation Forest", "#42A5F5"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["Date"], y=df[col],
                mode="lines", name=name,
                line=dict(width=1, color=color),
                stackgroup="one",
                hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
            ))
    if "ensemble_anomaly" in df.columns:
        anom = df[df["ensemble_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"], y=anom["ensemble_score"],
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, symbol="circle",
                            line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Component Score",
        title=dict(text=f"{ticker} — Do independent tests agree?", font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=10),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return fig.to_json()


def method_ewma_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """EWMA deviation chart showing price vs. trend and deviation %."""
    df = df_ticker.sort_values("Date").copy()
    if "deviation_pct" not in df.columns:
        return "{}"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.08, row_heights=[0.55, 0.45])

    # Top: price vs EWMA
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Close"], mode="lines", name="Price",
        line=dict(color=BLUE, width=1.5),
        hovertemplate="$%{y:,.2f}<extra></extra>",
    ), row=1, col=1)
    if "ewma_value" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"], y=df["ewma_value"], mode="lines", name="EWMA",
            line=dict(color=ORANGE, width=1.5, dash="dot"),
            hovertemplate="$%{y:,.2f}<extra></extra>",
        ), row=1, col=1)

    # Bottom: deviation % as bars colored by direction
    colors = [RED if d < -3 else ORANGE if d < 0 else TEAL if d > 3 else "#90CAF9"
              for d in df["deviation_pct"]]
    fig.add_trace(go.Bar(
        x=df["Date"], y=df["deviation_pct"], name="Deviation %",
        marker_color=colors,
        hovertemplate="%{x|%b %d, %Y}<br>%{y:+.1f}% from trend<extra></extra>",
    ), row=2, col=1)

    if "ewma_anomaly" in df.columns:
        anom = df[df["ewma_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"], y=anom["Close"],
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
            ), row=1, col=1)

    fig.update_layout(
        height=300, margin=dict(l=50, r=20, t=30, b=30),
        title=dict(text=f"{ticker} — Is momentum abnormal?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_yaxes(title_text="Price ($)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Deviation %", gridcolor=LIGHT_GRAY, row=2, col=1)
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    return fig.to_json()


# ---- Summary charts ----

def scoreboard_chart(results: pd.DataFrame) -> str:
    """Horizontal bar chart: latest consensus score per ticker, sorted by score."""
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
        xaxis_title="Anomaly Score (recent 5-day avg)",
        margin=dict(l=60, r=20, t=20, b=40),
        **LAYOUT_DEFAULTS,
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
    fig.add_trace(go.Scatter(
        x=dates, y=counts,
        mode="lines+markers", name="Anomalies",
        line=dict(color=RED, width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br><b>%{y} anomalies</b><extra></extra>",
    ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=20, b=30),
        yaxis_title="Anomalies Detected",
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return fig.to_json()
