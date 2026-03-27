"""Chart generation — Plotly figures for the Cool Runnings spam rate dashboard.

All charts use fig.to_plotly_json() (not fig.to_json()) to produce
plain-array JSON compatible with the Plotly.js CDN version loaded in the browser.
"""

import json
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# --- Color palette (Jamaica-inspired) ---
GREEN = "#009B3A"       # Jamaican green
GOLD = "#FED100"        # Jamaican gold
BLACK = "#1A1A1A"       # Near-black
RED = "#D50000"         # Danger
DARK_RED = "#B71C1C"    # Critical
ORANGE = "#FF6D00"      # Attention
DEEP_ORANGE = "#E65100" # Warning
BLUE = "#2962FF"        # Primary
TEAL = "#00897B"        # Accent
PURPLE = "#7C4DFF"      # Accent
GRAY = "#9E9E9E"
LIGHT_GRAY = "#E0E0E0"
LIGHT_BLUE = "#90CAF9"

SIGNAL_COLORS = {
    "WATCH": LIGHT_BLUE,
    "HEADS_UP": GOLD,
    "ATTENTION": ORANGE,
    "WARNING": DEEP_ORANGE,
    "URGENT": RED,
    "CRITICAL": DARK_RED,
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
)

# Google's spam rate threshold line
GOOGLE_THRESHOLD = 0.003  # 0.3%


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
    """Spam rate line with signal markers and Google threshold, score bars below."""
    df = df_domain.sort_values("Date").copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # --- Spam rate line (displayed as percentage) ---
    fig.add_trace(
        go.Scatter(
            x=df["Date"].tolist(),
            y=(df["SpamRate"] * 100).tolist(),
            mode="lines", name="Spam Rate",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{x|%b %d, %Y}<br><b>%{y:.3f}% spam rate</b><extra></extra>",
        ),
        row=1, col=1,
    )

    # --- EWMA trend line ---
    if "ewma_value" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"].tolist(),
                y=(df["ewma_value"] * 100).tolist(),
                mode="lines", name="Trend (EWMA)",
                line=dict(color=ORANGE, width=1.5, dash="dot"),
                hovertemplate="%{x|%b %d, %Y}<br>Trend: %{y:.3f}%<extra></extra>",
            ),
            row=1, col=1,
        )

    # --- Google 0.3% threshold line ---
    fig.add_hline(
        y=GOOGLE_THRESHOLD * 100,
        line_dash="dash",
        line_color=RED,
        line_width=1,
        annotation_text="Google 0.3% threshold",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color=RED,
        row=1, col=1,
    )

    # --- Signal markers ON the spam rate line ---
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
                label = sig_type.replace("_", " ").title()
                is_severe = sig_type in ("URGENT", "CRITICAL", "WARNING")
                fig.add_trace(
                    go.Scatter(
                        x=subset["Date"].tolist(),
                        y=(subset["SpamRate"] * 100).tolist(),
                        mode="markers",
                        name=label,
                        marker=dict(
                            color=color,
                            size=11 if is_severe else 8,
                            symbol="circle",
                            line=dict(width=2, color="white"),
                        ),
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "%{x|%b %d, %Y}<br>"
                            "%{y:.3f}% spam rate<extra></extra>"
                        ),
                    ),
                    row=1, col=1,
                )
    elif "consensus_anomaly" in df.columns:
        anomalies = df[df["consensus_anomaly"] == True]
        if not anomalies.empty:
            fig.add_trace(
                go.Scatter(
                    x=anomalies["Date"].tolist(),
                    y=(anomalies["SpamRate"] * 100).tolist(),
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
                    RED if s > 0.6 else ORANGE if s > 0.4 else GOLD if s > 0.2 else LIGHT_GRAY
                    for s in scores
                ],
                hovertemplate="%{x|%b %d, %Y}<br>Score: %{y:.3f}<extra></extra>",
            ),
            row=2, col=1,
        )

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
    fig.update_yaxes(title_text="Spam Rate (%)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=LIGHT_GRAY, row=2, col=1)

    return _fig_to_json(fig)


# ---- Per-method detail charts ----

def method_fourier_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Fourier score over time — Feel the Rhythm."""
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
                hovertemplate="<b>Rhythm Changed!</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Spectral Divergence",
        title=dict(text="Feel the Rhythm — Has the spam rate pattern changed?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_mp_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Matrix Profile score over time — Feel the Rhyme."""
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
                hovertemplate="<b>New Rhyme!</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Nearest-Neighbor Distance",
        title=dict(text="Feel the Rhyme — Is this something we've never seen before?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_ensemble_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """Ensemble score with component breakdown — Get on Up."""
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
                hovertemplate="<b>Tests Agree!</b><br>%{x|%b %d, %Y}<br>Score: %{y:.4f}<extra></extra>",
            ))
    fig.update_layout(
        height=250, margin=dict(l=50, r=20, t=30, b=30),
        yaxis_title="Component Score",
        title=dict(text="Get on Up — Do three independent check-ups agree?", font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=10),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_ewma_chart(df_domain: pd.DataFrame, domain: str) -> str:
    """EWMA deviation chart — It's Bobsled Time."""
    df = df_domain.sort_values("Date").copy()
    if "deviation_pct" not in df.columns:
        return "{}"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.08, row_heights=[0.55, 0.45])

    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=(df["SpamRate"] * 100).tolist(),
        mode="lines", name="Spam Rate",
        line=dict(color=BLUE, width=1.5),
        hovertemplate="%{y:.3f}%<extra></extra>",
    ), row=1, col=1)
    if "ewma_value" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"].tolist(), y=(df["ewma_value"] * 100).tolist(),
            mode="lines", name="EWMA",
            line=dict(color=ORANGE, width=1.5, dash="dot"),
            hovertemplate="%{y:.3f}%<extra></extra>",
        ), row=1, col=1)

    devs = df["deviation_pct"].tolist()
    colors = [RED if d > 5 else ORANGE if d > 0 else GREEN if d < -5 else LIGHT_BLUE
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
                x=anom["Date"].tolist(), y=(anom["SpamRate"] * 100).tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
            ), row=1, col=1)

    fig.update_layout(
        height=300, margin=dict(l=50, r=20, t=30, b=30),
        title=dict(text="It's Bobsled Time — Is the trend picking up speed?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_yaxes(title_text="Spam Rate (%)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Deviation %", gridcolor=LIGHT_GRAY, row=2, col=1)
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


# ---- Summary charts ----

def overall_spam_rate_chart(results: pd.DataFrame) -> str:
    """Overall spam rate: daily average across all domains with linear trend line.

    Shows the past 6 months of average spam rate with a linear regression fit.
    """
    df = results[["Date", "SpamRate"]].copy()
    daily_avg = df.groupby("Date")["SpamRate"].mean().reset_index().sort_values("Date")

    # Last 6 months
    cutoff = daily_avg["Date"].max() - pd.Timedelta(days=180)
    daily_avg = daily_avg[daily_avg["Date"] >= cutoff]

    if daily_avg.empty:
        return "{}"

    dates = daily_avg["Date"].tolist()
    rates = (daily_avg["SpamRate"] * 100).tolist()

    fig = go.Figure()

    # Daily average line
    fig.add_trace(go.Scatter(
        x=dates, y=rates,
        mode="lines", name="Daily Average",
        line=dict(color=BLUE, width=2),
        hovertemplate="%{x|%b %d, %Y}<br><b>%{y:.3f}%</b><extra></extra>",
    ))

    # Linear trend fit
    x_numeric = np.arange(len(daily_avg))
    y_values = daily_avg["SpamRate"].values * 100
    mask = ~np.isnan(y_values)
    if mask.sum() >= 2:
        coeffs = np.polyfit(x_numeric[mask], y_values[mask], 1)
        trend_line = np.polyval(coeffs, x_numeric)
        slope_direction = "increasing" if coeffs[0] > 0 else "decreasing"
        fig.add_trace(go.Scatter(
            x=dates, y=trend_line.tolist(),
            mode="lines", name=f"Trend ({slope_direction})",
            line=dict(color=GOLD if coeffs[0] > 0 else GREEN, width=2, dash="dash"),
            hovertemplate="Trend: %{y:.3f}%<extra></extra>",
        ))

    # Google 0.3% threshold
    fig.add_hline(
        y=GOOGLE_THRESHOLD * 100,
        line_dash="dot", line_color=RED, line_width=1,
        annotation_text="0.3% threshold",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color=RED,
    )

    fig.update_layout(
        height=300,
        margin=dict(l=50, r=20, t=25, b=30),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        hovermode="x unified",
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(title_text="Spam Rate (%)", gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


# ---- Country distribution pie charts ----

# Consistent colors per country
COUNTRY_COLORS = {
    "US": "#FF8A80",   # Salmon/pink (like the image)
    "GB": "#FFB74D",   # Orange
    "IN": "#CE93D8",   # Purple
    "ZA": "#90CAF9",   # Blue
    "Other": "#A5D6A7", # Green
}


def country_pie_chart(country_data: dict[str, int], title: str, border_color: str) -> str:
    """Single pie chart showing proportion of total sends by country."""
    if not country_data:
        return "{}"

    countries = list(country_data.keys())
    values = list(country_data.values())
    colors = [COUNTRY_COLORS.get(c, GRAY) for c in countries]

    fig = go.Figure(data=[go.Pie(
        labels=countries,
        values=values,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="percent",
        textposition="inside",
        textfont=dict(size=11, color="white"),
        hovertemplate="<b>%{label}</b><br>Sent: %{value:,.0f}<br>%{percent}<extra></extra>",
        sort=False,
        hole=0.03,
    )])

    fig.update_layout(
        title=dict(text=title, font_size=12, x=0.5, xanchor="center"),
        height=350,
        margin=dict(l=20, r=20, t=60, b=20),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05,
            xanchor="center",
            x=0.5,
            font_size=11,
        ),
        **LAYOUT_DEFAULTS,
    )
    return _fig_to_json(fig)
