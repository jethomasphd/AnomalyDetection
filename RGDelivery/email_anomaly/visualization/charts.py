"""Chart generation — Plotly figures for the email click anomaly dashboard.

IMPORTANT: All charts use fig.to_plotly_json() (not fig.to_json()) to produce
plain-array JSON compatible with the Plotly.js CDN version loaded in the browser.
"""

import json
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
GREEN = "#00C853"

SIGNAL_COLORS = {
    "WARM": GREEN,
    "THROTTLE": ORANGE,
    "PAUSE": RED,
    "INVESTIGATE": PURPLE,
    "AUDIT": AMBER,
    "QUARANTINE": "#FF8F00",
    "LOCKDOWN": RED,
    "WATCH": "#42A5F5",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
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


def domain_chart(df_domain: pd.DataFrame, domain: str, signals: list[dict] | None = None) -> str:
    """Click line with signal markers drawn directly on the line, score bars below."""
    df = df_domain.sort_values("Date").copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # --- Click line ---
    fig.add_trace(
        go.Scatter(
            x=df["Date"].tolist(), y=df["Clicks"].tolist(),
            mode="lines", name="Clicks",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{x|%b %d, %Y}<br><b>%{y:,} clicks</b><extra></extra>",
        ),
        row=1, col=1,
    )

    # --- EWMA trend line ---
    if "ewma_value" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"].tolist(), y=df["ewma_value"].tolist(),
                mode="lines", name="Trend (EWMA)",
                line=dict(color=ORANGE, width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>Trend: %{y:,.0f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # --- Signal markers ON the click line ---
    if signals and "consensus_anomaly" in df.columns:
        sig_lookup = {}
        for s in signals:
            if s["domain"] == domain:
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
                        x=subset["Date"].tolist(), y=subset["Clicks"].tolist(),
                        mode="markers",
                        name=label,
                        marker=dict(
                            color=color,
                            size=11 if sig_type in ("PAUSE", "LOCKDOWN", "THROTTLE", "QUARANTINE") else 8,
                            symbol="circle",
                            line=dict(width=2, color="white"),
                        ),
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "%{x|%b %d, %Y}<br>"
                            "%{y:,} clicks<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )
    elif "consensus_anomaly" in df.columns:
        anomalies = df[df["consensus_anomaly"] == True]
        if not anomalies.empty:
            fig.add_trace(
                go.Scatter(
                    x=anomalies["Date"].tolist(), y=anomalies["Clicks"].tolist(),
                    mode="markers", name="Anomaly",
                    marker=dict(color=RED, size=9, symbol="circle",
                                line=dict(width=2, color="white")),
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
                    RED if s > 0.6 else ORANGE if s > 0.4 else AMBER if s > 0.2 else LIGHT_GRAY
                    for s in scores
                ],
                hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.3f}<extra></extra>",
            ),
            row=2, col=1,
        )

    # Truncate long domain names for the title
    display_name = domain if len(domain) <= 40 else domain[:37] + "..."
    fig.update_layout(
        title=dict(text=display_name, font_size=15, x=0.01),
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        margin=dict(l=55, r=20, t=45, b=30),
        hovermode="x unified",
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(title_text="Clicks", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=LIGHT_GRAY, row=2, col=1)

    return _fig_to_json(fig)


# ---- Per-method detail charts ----

def method_fourier_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Fourier score over time with anomaly threshold region."""
    df = df_domain.sort_values("Date").copy()
    if "fourier_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["fourier_score"].tolist(),
        mode="lines", name="Fourier Score",
        line=dict(color=PURPLE, width=1.5),
        fill="tozeroy", fillcolor="rgba(124,77,255,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    if "fourier_anomaly" in df.columns:
        anom = df[df["fourier_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["fourier_score"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Spectral Divergence",
        title=dict(text="Has the engagement rhythm changed?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_mp_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Matrix Profile score over time."""
    df = df_domain.sort_values("Date").copy()
    if "mp_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["mp_score"].tolist(),
        mode="lines", name="Matrix Profile Score",
        line=dict(color=TEAL, width=1.5),
        fill="tozeroy", fillcolor="rgba(0,137,123,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
    ))
    if "mp_anomaly" in df.columns:
        anom = df[df["mp_anomaly"] == True]
        if not anom.empty:
            fig.add_trace(go.Scatter(
                x=anom["Date"].tolist(), y=anom["mp_score"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Nearest-Neighbor Distance",
        title=dict(text="Never-before-seen click pattern?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_ensemble_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Ensemble score with component breakdown."""
    df = df_domain.sort_values("Date").copy()
    if "ensemble_score" not in df.columns:
        return "{}"

    fig = go.Figure()
    for col, name, color in [
        ("zscore_component", "Z-Score", "#EF5350"),
        ("seasonal_component", "Seasonal", "#FFA726"),
        ("iforest_component", "Isolation Forest", "#42A5F5"),
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
                marker=dict(color=RED, size=7, symbol="circle",
                            line=dict(width=1, color="white")),
                hovertemplate="<b>Flagged</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Component Score",
        title=dict(text="Do independent tests agree?", font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=10),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_ewma_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """EWMA deviation chart showing clicks vs. trend and deviation %."""
    df = df_domain.sort_values("Date").copy()
    if "deviation_pct" not in df.columns:
        return "{}"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.08, row_heights=[0.55, 0.45])

    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["Clicks"].tolist(), mode="lines", name="Clicks",
        line=dict(color=BLUE, width=1.5),
        hovertemplate="%{y:,}<extra></extra>",
    ), row=1, col=1)
    if "ewma_value" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"].tolist(), y=df["ewma_value"].tolist(), mode="lines", name="EWMA",
            line=dict(color=ORANGE, width=1.5, dash="dot"),
            hovertemplate="%{y:,.0f}<extra></extra>",
        ), row=1, col=1)

    devs = df["deviation_pct"].tolist()
    colors = [RED if d < -3 else ORANGE if d < 0 else TEAL if d > 3 else "#90CAF9"
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
                x=anom["Date"].tolist(), y=anom["Clicks"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
            ), row=1, col=1)

    fig.update_layout(
        height=300, margin=dict(l=50, r=20, t=30, b=30),
        title=dict(text="Is click momentum abnormal?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_yaxes(title_text="Clicks", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Deviation %", gridcolor=LIGHT_GRAY, row=2, col=1)
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


# ---- Summary charts ----

def scoreboard_chart(results: pd.DataFrame) -> str:
    """Horizontal bar chart: latest consensus score per domain, sorted by score."""
    latest = results.sort_values("Date").groupby("Domain").tail(5)
    avg_recent = latest.groupby("Domain")["consensus_score"].mean().sort_values(ascending=True)

    # Truncate long domain names for display
    labels = [d if len(d) <= 35 else d[:32] + "..." for d in avg_recent.index]
    scores = avg_recent.values.tolist()

    colors = [
        RED if s > 0.5 else ORANGE if s > 0.35 else AMBER if s > 0.2 else "#90CAF9"
        for s in scores
    ]

    fig = go.Figure(
        go.Bar(
            x=scores,
            y=labels,
            orientation="h",
            marker_color=colors,
            hovertemplate="<b>%{y}</b><br>Score: %{x:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, len(avg_recent) * 36 + 80),
        xaxis_title="Anomaly Score (recent 5-day avg)",
        margin=dict(l=250, r=20, t=20, b=40),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY, range=[0, max(max(scores) * 1.1, 0.1)])
    return _fig_to_json(fig)
