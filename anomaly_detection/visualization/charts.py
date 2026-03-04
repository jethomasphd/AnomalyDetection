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
    "BUY": GREEN,
    "SELL": RED,
    "LONG": TEAL,
    "SHORT": ORANGE,
    "REDUCE": AMBER,
    "WATCH": "#42A5F5",
}

LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
)


def _fig_to_json(fig) -> str:
    """Serialize a Plotly figure to JSON with plain arrays (no bdata).

    Uses a custom encoder to handle pandas Timestamps and numpy types
    that to_plotly_json() leaves as native objects.
    """
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
            line=dict(color=BLUE, width=2),
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
                line=dict(color=ORANGE, width=1.5, dash="dot"),
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
                            line=dict(width=2, color="white"),
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
    fig.update_yaxes(title_text="Price ($)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Score", gridcolor=LIGHT_GRAY, row=2, col=1)

    return _fig_to_json(fig)


# ---- Per-method detail charts ----

def method_fourier_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Fourier score over time with anomaly threshold region."""
    df = df_ticker.sort_values("Date").copy()
    if "fourier_score" not in df.columns:
        return "{}"
    display = ticker_display(ticker)

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
        title=dict(text="Has the rhythm changed?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_mp_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Matrix Profile score over time."""
    df = df_ticker.sort_values("Date").copy()
    if "mp_score" not in df.columns:
        return "{}"
    display = ticker_display(ticker)

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
        title=dict(text="Never-before-seen pattern?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


def method_ensemble_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """Ensemble score with component breakdown."""
    df = df_ticker.sort_values("Date").copy()
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


def method_ewma_chart(df_ticker: pd.DataFrame, ticker: str) -> str:
    """EWMA deviation chart showing price vs. trend and deviation %."""
    df = df_ticker.sort_values("Date").copy()
    if "deviation_pct" not in df.columns:
        return "{}"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.08, row_heights=[0.55, 0.45])

    fig.add_trace(go.Scatter(
        x=df["Date"].tolist(), y=df["Close"].tolist(), mode="lines", name="Price",
        line=dict(color=BLUE, width=1.5),
        hovertemplate="$%{y:,.2f}<extra></extra>",
    ), row=1, col=1)
    if "ewma_value" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"].tolist(), y=df["ewma_value"].tolist(), mode="lines", name="EWMA",
            line=dict(color=ORANGE, width=1.5, dash="dot"),
            hovertemplate="$%{y:,.2f}<extra></extra>",
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
                x=anom["Date"].tolist(), y=anom["Close"].tolist(),
                mode="markers", name="Flagged",
                marker=dict(color=RED, size=7, line=dict(width=1, color="white")),
            ), row=1, col=1)

    fig.update_layout(
        height=300, margin=dict(l=50, r=20, t=30, b=30),
        title=dict(text="Is momentum abnormal?", font_size=13),
        showlegend=False, **LAYOUT_DEFAULTS,
    )
    fig.update_yaxes(title_text="Price ($)", gridcolor=LIGHT_GRAY, row=1, col=1)
    fig.update_yaxes(title_text="Deviation %", gridcolor=LIGHT_GRAY, row=2, col=1)
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)


# ---- Summary charts ----

def scoreboard_chart(results: pd.DataFrame) -> str:
    """Horizontal bar chart: latest consensus score per ticker, sorted by score."""
    latest = results.sort_values("Date").groupby("Ticker").tail(5)
    avg_recent = latest.groupby("Ticker")["consensus_score"].mean().sort_values(ascending=True)

    labels = [ticker_display(t) for t in avg_recent.index]
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
        margin=dict(l=140, r=20, t=20, b=40),
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY, range=[0, max(max(scores) * 1.1, 0.1)])
    return _fig_to_json(fig)


# ---- Attention Queue data (rendered as HTML table in template) ----

def compute_attention_queue(results: pd.DataFrame, alerts: list[dict]) -> list[dict]:
    """Compute an attention-ranked list of tickers for the Attention Queue.

    Attention Score = weighted function of:
      - recency: days since last anomaly (lower = higher attention)
      - severity: max consensus_score in recent window
      - persistence: streak of consecutive anomaly days
      - signal strength: actionable signal > watch > none

    Returns a list of dicts sorted by attention_score descending.
    """
    if results.empty:
        return []

    today = results["Date"].max()
    queue = []

    # Build signal lookup
    sig_lookup = {}
    for a in alerts:
        key = a["ticker"]
        if key not in sig_lookup or a["date"] > sig_lookup[key]["date"]:
            sig_lookup[key] = a

    for ticker, grp in results.groupby("Ticker"):
        g = grp.sort_values("Date")
        anomalies = g[g.get("consensus_anomaly", False) == True]

        # Recency: days since last anomaly
        if not anomalies.empty:
            last_anomaly_date = anomalies["Date"].max()
            days_since = (today - last_anomaly_date).days
        else:
            last_anomaly_date = None
            days_since = 999

        # Severity: max score in last 14 days
        recent = g[g["Date"] >= today - pd.Timedelta(days=14)]
        max_severity = float(recent["consensus_score"].max()) if not recent.empty else 0

        # Persistence: count consecutive anomaly days at end of series
        streak = 0
        if "consensus_anomaly" in g.columns:
            for val in reversed(g["consensus_anomaly"].tolist()):
                if val:
                    streak += 1
                else:
                    break

        # Signal strength
        sig = sig_lookup.get(ticker)
        signal_type = sig["signal"] if sig else None
        signal_weight = 0
        if signal_type in ("BUY", "SELL", "LONG", "SHORT"):
            signal_weight = 1.0
        elif signal_type in ("REDUCE",):
            signal_weight = 0.7
        elif signal_type in ("WATCH",):
            signal_weight = 0.3

        # Composite attention score (0-100 scale)
        recency_score = max(0, 1 - days_since / 30) * 30  # 0-30 pts
        severity_score_pts = min(max_severity * 40, 40)     # 0-40 pts
        persistence_score = min(streak * 5, 15)             # 0-15 pts
        signal_score = signal_weight * 15                   # 0-15 pts
        attention_score = recency_score + severity_score_pts + persistence_score + signal_score

        # Sparkline data: last 30 days of consensus_score
        last_30 = g.tail(30)
        sparkline = last_30["consensus_score"].tolist() if "consensus_score" in g.columns else []

        # Category
        reg = TICKER_REGISTRY.get(ticker, {})
        category = reg.get("category", "")

        # Change vs prior day
        if len(g) >= 2 and "consensus_score" in g.columns:
            latest_score = float(g["consensus_score"].iloc[-1])
            prev_score = float(g["consensus_score"].iloc[-2])
            change = latest_score - prev_score
        else:
            latest_score = max_severity
            change = 0

        queue.append({
            "rank": 0,  # filled below
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

    # Sort by attention score descending
    queue.sort(key=lambda x: x["attention_score"], reverse=True)
    for i, item in enumerate(queue):
        item["rank"] = i + 1

    return queue


# ---- Backtest: 3-month signal-following performance ----

def compute_backtest(results: pd.DataFrame, alerts: list[dict]) -> dict:
    """Compute a simple 3-month backtest of following the dashboard's signals.

    Strategy assumptions:
      - Buy at close on day of BUY/LONG signal
      - Sell at close on day of SELL/SHORT signal
      - Hold otherwise
      - Start with $10,000 per ticker, equal-weight portfolio

    Returns:
      {
        "per_ticker": [{ticker, pct_return, n_trades, equity_curve, ...}],
        "portfolio": {pct_return, equity_curve, max_drawdown, win_rate, n_trades},
        "start_date": ..., "end_date": ...
      }
    """
    if results.empty or not alerts:
        return {"per_ticker": [], "portfolio": {}, "start_date": None, "end_date": None}

    today = results["Date"].max()
    start = today - pd.Timedelta(days=90)

    # Filter alerts to last 3 months
    start_str = start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start)[:10]
    recent_alerts = [a for a in alerts if a["date"] >= start_str]

    if not recent_alerts:
        return {"per_ticker": [], "portfolio": {}, "start_date": str(start)[:10], "end_date": str(today)[:10]}

    # Build per-ticker signal timeline
    tickers_with_signals = set()
    sig_timeline = {}  # {ticker: {date_str: signal}}
    for a in recent_alerts:
        t = a["ticker"]
        tickers_with_signals.add(t)
        sig_timeline.setdefault(t, {})[a["date"]] = a["signal"]

    per_ticker = []
    all_equity_curves = {}
    initial_capital = 10000

    for ticker in tickers_with_signals:
        grp = results[results["Ticker"] == ticker].sort_values("Date")
        grp = grp[grp["Date"] >= start].copy()
        if grp.empty or len(grp) < 2:
            continue

        dates = grp["Date"].tolist()
        closes = grp["Close"].tolist()
        signals = sig_timeline.get(ticker, {})

        # Simulate
        cash = initial_capital
        shares = 0
        equity_curve = []
        trades = []
        position = "out"  # out or long

        for i, (d, c) in enumerate(zip(dates, closes)):
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
            sig = signals.get(d_str)

            if sig in ("BUY", "LONG") and position == "out" and c > 0:
                shares = cash / c
                cash = 0
                position = "long"
                trades.append({"date": d_str, "action": "buy", "price": c})
            elif sig in ("SELL", "SHORT") and position == "long":
                cash = shares * c
                shares = 0
                position = "out"
                trades.append({"date": d_str, "action": "sell", "price": c})

            portfolio_value = cash + shares * c
            equity_curve.append({"date": d_str, "value": round(portfolio_value, 2)})

        # Final value
        final_value = cash + shares * closes[-1]
        pct_return = (final_value - initial_capital) / initial_capital * 100

        # Win rate from completed trades
        wins = 0
        total_round_trips = 0
        for j in range(0, len(trades) - 1, 2):
            if j + 1 < len(trades):
                buy_price = trades[j]["price"]
                sell_price = trades[j + 1]["price"]
                total_round_trips += 1
                if sell_price > buy_price:
                    wins += 1

        per_ticker.append({
            "ticker": ticker,
            "display": ticker_display(ticker),
            "pct_return": round(pct_return, 2),
            "n_trades": len(trades),
            "win_rate": round(wins / total_round_trips * 100, 1) if total_round_trips > 0 else None,
            "equity_curve": equity_curve,
            "final_value": round(final_value, 2),
        })
        all_equity_curves[ticker] = {e["date"]: e["value"] for e in equity_curve}

    # Portfolio equity curve (equal-weight average)
    if per_ticker:
        all_dates = sorted(set(d for curves in all_equity_curves.values() for d in curves))
        portfolio_curve = []
        for d in all_dates:
            values = [curves.get(d) for curves in all_equity_curves.values() if curves.get(d) is not None]
            if values:
                portfolio_curve.append({"date": d, "value": round(sum(values) / len(values), 2)})

        # Portfolio stats
        if portfolio_curve:
            start_val = portfolio_curve[0]["value"]
            end_val = portfolio_curve[-1]["value"]
            pct_return = (end_val - start_val) / start_val * 100

            # Max drawdown
            peak = portfolio_curve[0]["value"]
            max_dd = 0
            for p in portfolio_curve:
                if p["value"] > peak:
                    peak = p["value"]
                dd = (peak - p["value"]) / peak * 100
                if dd > max_dd:
                    max_dd = dd

            total_trades = sum(t["n_trades"] for t in per_ticker)
            wins_total = sum(1 for t in per_ticker if t["pct_return"] > 0)

            portfolio_stats = {
                "pct_return": round(pct_return, 2),
                "max_drawdown": round(max_dd, 2),
                "n_trades": total_trades,
                "win_rate": round(wins_total / len(per_ticker) * 100, 1) if per_ticker else 0,
                "equity_curve": portfolio_curve,
            }
        else:
            portfolio_stats = {}
    else:
        portfolio_stats = {}

    return {
        "per_ticker": sorted(per_ticker, key=lambda x: x["pct_return"], reverse=True),
        "portfolio": portfolio_stats,
        "start_date": str(start)[:10],
        "end_date": str(today)[:10],
    }


def backtest_equity_chart(backtest: dict) -> str:
    """Generate a portfolio equity curve chart from backtest results."""
    portfolio = backtest.get("portfolio", {})
    curve = portfolio.get("equity_curve", [])
    if not curve:
        return "{}"

    dates = [p["date"] for p in curve]
    values = [p["value"] for p in curve]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines", name="Portfolio Value",
        line=dict(color=BLUE, width=2),
        fill="tozeroy", fillcolor="rgba(41,98,255,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br><b>$%{y:,.2f}</b><extra></extra>",
    ))

    # Add a reference line at starting value
    if values:
        fig.add_hline(y=values[0], line_dash="dot", line_color=GRAY,
                      annotation_text=f"Start: ${values[0]:,.0f}")

    fig.update_layout(
        height=300,
        margin=dict(l=60, r=20, t=30, b=30),
        yaxis_title="Portfolio Value ($)",
        title=dict(text="Equal-Weight Signal Portfolio (3 months)", font_size=13),
        showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    fig.update_xaxes(gridcolor=LIGHT_GRAY)
    fig.update_yaxes(gridcolor=LIGHT_GRAY)
    return _fig_to_json(fig)
