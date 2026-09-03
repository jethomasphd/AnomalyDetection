"""Build the investment prospectus for THE SIGNAL from the committed record.

Every figure in the document is derived from files that the daily pipeline
commits — the signals ledger, the run history, run health, and the walk-forward
backtest that the dashboard renders. Nothing is typed in by hand, so the
prospectus can be regenerated after any run:

    python reports/prospectus/build_prospectus.py            # HTML only
    python reports/prospectus/build_prospectus.py --pdf      # + PDF via Chromium

Inputs (all relative to the repository root):
    docs/index.html                 rendered dashboard — the backtest equity
                                    curve, benchmark curve, and trade ledger
    data/ledger/signals.jsonl       the full, append-only signal ledger
    data/history/run_<date>.json    latest run summary
    data/run_health.json            fetch coverage, basis breaks, stale feeds
    data/alerts.json                run block + per-ticker status
    anomaly_detection/config.py     universe registry + protocol parameters

Outputs:
    reports/prospectus/The_Signal_Prospectus.html
    reports/prospectus/The_Signal_Prospectus.pdf   (with --pdf)
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import html as htmlmod
import json
import math
import os
import re
import statistics as st
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from anomaly_detection import config as cfg  # noqa: E402


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _read_json(path):
    with open(path) as f:
        return json.load(f)


def load_backtest_from_dashboard(path: str) -> dict:
    """Recover the walk-forward backtest that the dashboard rendered.

    The pipeline serialises the equity/benchmark/drawdown series into the
    Plotly figure and the trade ledger into a table; both are parsed here so
    the prospectus reports exactly what the dashboard reports.
    """
    chart_line = None
    ledger_lines: list[str] = []
    banner: list[str] = []
    in_ledger = in_banner = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("const backtestChartData ="):
                chart_line = s
            if "Trade Ledger" in s and not in_ledger and "<p" in s or s == "Trade Ledger":
                in_ledger = True
            if in_ledger:
                ledger_lines.append(s)
                if "Simulation for educational purposes" in s:
                    in_ledger = False
            if 'class="bl-headline"' in s:
                in_banner = True
            if in_banner:
                banner.append(s)
                if 'class="bl-sub"' in s:
                    pass
                if s == "</div>" and any("bl-sub" in b for b in banner):
                    in_banner = False
    if chart_line is None:
        raise SystemExit("backtest chart data not found in docs/index.html")

    fig = json.loads(chart_line.split("=", 1)[1].strip().rstrip(";"))
    curve: dict = {}
    for t in fig["data"]:
        name = t.get("name", "")
        if name == "Strategy":
            curve["dates"], curve["equity"] = t["x"], t["y"]
        elif "baseline" in name:
            curve["bench_equity"] = t["y"]
            curve["baseline_ticker"] = name.split()[0]
        elif name == "Drawdown":
            curve["drawdown"] = t.get("customdata")

    raw = "\n".join(ledger_lines)
    rows = re.findall(
        r"<tr onclick=\"selectTicker\('([A-Z0-9\-\.\^]+)'\)\"[^>]*>(.*?)</tr>", raw, flags=re.S)
    trades = []
    for tk, body in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", body, flags=re.S)
        clean = [re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", "", td))).strip() for td in tds]
        entry, exit_, status, disp, action, epx, xpx, pnl, pct, reason, methods = clean
        basis = None
        m = re.search(r"×([\d\.]+) adj", epx)
        if m:
            basis = float(m.group(1))
            epx = epx.split("×")[0].strip()
        trades.append({
            "ticker": tk, "display": disp, "entry_date": entry,
            "exit_date": None if exit_ in ("—", "-", "") else exit_,
            "status": status, "action": action,
            "entry_price": float(epx.replace("$", "").replace(",", "")),
            "exit_price": float(xpx.replace("$", "").replace(",", "")),
            "dollar_gain": float(pnl.replace("$", "").replace(",", "").replace("+", "")),
            "pct_change": float(pct.replace("%", "").replace("+", "")),
            "exit_reason": reason, "methods": methods, "basis_factor": basis,
        })
    banner_text = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", "\n".join(banner))))
    m = re.search(r"(\d+) skipped", banner_text)
    n_skipped_banner = int(m.group(1)) if m else None
    return {"curve": curve, "trades": trades, "n_skipped_banner": n_skipped_banner}


def load_signals(path: str) -> list[dict]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if isinstance(rec.get("rationale"), str):
                try:
                    rec["rationale"] = json.loads(rec["rationale"])
                except json.JSONDecodeError:
                    rec["rationale"] = {}
            out.append(rec)
    return out


def latest_run_summary(history_dir: str) -> dict:
    runs = sorted(f for f in os.listdir(history_dir) if f.startswith("run_") and f.endswith(".json"))
    return _read_json(os.path.join(history_dir, runs[-1]))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _returns(v):
    return [v[i] / v[i - 1] - 1 for i in range(1, len(v))]


def _years_between(d0: str, d1: str) -> float:
    return (dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days / 365.25


def _max_drawdown(v, dates):
    peak, pk_i, mdd, mdd_pk, mdd_tr = v[0], 0, 0.0, 0, 0
    for i, x in enumerate(v):
        if x > peak:
            peak, pk_i = x, i
        dd = (peak - x) / peak
        if dd > mdd:
            mdd, mdd_pk, mdd_tr = dd, pk_i, i
    rec = None
    for i in range(mdd_tr, len(v)):
        if v[i] >= v[mdd_pk]:
            rec = i
            break
    return {
        "pct": mdd, "dollars": v[mdd_pk] - v[mdd_tr],
        "peak_date": dates[mdd_pk], "trough_date": dates[mdd_tr],
        "recovery_date": dates[rec] if rec is not None else None,
        "days_to_trough": (dt.date.fromisoformat(dates[mdd_tr]) - dt.date.fromisoformat(dates[mdd_pk])).days,
        "days_to_recover": ((dt.date.fromisoformat(dates[rec]) - dt.date.fromisoformat(dates[mdd_tr])).days
                            if rec is not None else None),
    }


def series_stats(v, dates) -> dict:
    r = _returns(v)
    mu, sd = st.mean(r), st.stdev(r)
    yrs = _years_between(dates[0], dates[-1])
    cagr = (v[-1] / v[0]) ** (1 / yrs) - 1
    neg = [x for x in r if x < 0]
    dsd = math.sqrt(sum(x * x for x in neg) / len(r)) if neg else 0.0
    mdd = _max_drawdown(v, dates)
    return {
        "start": v[0], "end": v[-1], "total": v[-1] / v[0] - 1, "cagr": cagr, "years": yrs,
        "vol": sd * math.sqrt(252), "sharpe": mu / sd * math.sqrt(252) if sd else None,
        "sortino": mu / dsd * math.sqrt(252) if dsd else None,
        "max_dd": mdd, "calmar": cagr / mdd["pct"] if mdd["pct"] else None,
        "best_day": max(r), "worst_day": min(r),
        "best_day_date": dates[r.index(max(r)) + 1], "worst_day_date": dates[r.index(min(r)) + 1],
        "returns": r,
    }


def relative_stats(rs, rb) -> dict:
    ms, mb = st.mean(rs), st.mean(rb)
    cov = sum((a - ms) * (b - mb) for a, b in zip(rs, rb)) / (len(rs) - 1)
    beta = cov / st.variance(rb)
    corr = cov / (st.stdev(rs) * st.stdev(rb))
    active = [a - b for a, b in zip(rs, rb)]
    te = st.stdev(active) * math.sqrt(252)
    up = [(a, b) for a, b in zip(rs, rb) if b > 0]
    dn = [(a, b) for a, b in zip(rs, rb) if b < 0]
    return {
        "beta": beta, "corr": corr, "tracking_error": te,
        "info_ratio": st.mean(active) * 252 / te if te else None,
        "alpha_ann": (ms - beta * mb) * 252,
        "up_capture": sum(a for a, _ in up) / sum(b for _, b in up) if up else None,
        "down_capture": sum(a for a, _ in dn) / sum(b for _, b in dn) if dn else None,
    }


def monthly_returns(dates, v) -> "collections.OrderedDict[str, float]":
    ends: dict[str, float] = {}
    for d, x in zip(dates, v):
        ends[d[:7]] = x
    out = collections.OrderedDict()
    prev = v[0]
    for m, x in ends.items():
        out[m] = x / prev - 1
        prev = x
    return out


def calendar_years(dates, v):
    out = []
    for y in sorted({d[:4] for d in dates}):
        idx = [i for i, d in enumerate(dates) if d.startswith(y)]
        base = v[idx[0] - 1] if idx[0] > 0 else v[0]
        out.append({"year": y, "ret": v[idx[-1]] / base - 1,
                    "from": dates[idx[0]], "to": dates[idx[-1]],
                    "partial": not (dates[idx[0]][5:] <= "01-05" and dates[idx[-1]][5:] >= "12-28")})
    return out


def match_trades_to_signals(trades, buy_signals):
    """Attach each funded trade to the BUY signal it executed (the latest
    BUY on that ticker detected strictly before the fill date)."""
    by_ticker: dict[str, list[dict]] = collections.defaultdict(list)
    for s in buy_signals:
        by_ticker[s["ticker"]].append(s)
    for v in by_ticker.values():
        v.sort(key=lambda s: s.get("detected_at") or s["date"])
    used = set()
    for t in trades:
        cands = [s for s in by_ticker.get(t["ticker"], [])
                 if (s.get("detected_at") or s["date"]) < t["entry_date"] and id(s) not in used]
        if cands:
            s = cands[-1]
            used.add(id(s))
            t["signal_date"] = s["date"]
            t["dev_z"] = s.get("rationale", {}).get("details", {}).get("dev_z")
            t["deviation_pct"] = s.get("rationale", {}).get("details", {}).get("deviation_pct")
            t["provenance"] = s.get("provenance")
            t["confidence"] = s.get("confidence")
    return used


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def money(x, signed=False, decimals=0):
    if x is None:
        return "—"
    s = f"{abs(x):,.{decimals}f}"
    if x < 0:
        return f"−${s}"
    return f"+${s}" if signed else f"${s}"


def pct(x, signed=True, decimals=1):
    if x is None:
        return "—"
    v = x * 100
    s = f"{abs(v):.{decimals}f}%"
    if v < 0:
        return "−" + s
    return ("+" + s) if signed else s


def pp(x, decimals=1):
    v = x * 100
    return ("−" if v < 0 else "+") + f"{abs(v):.{decimals}f} pp"


def num(x, decimals=2):
    return "—" if x is None else f"{x:,.{decimals}f}"


def longdate(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%-d %B %Y")


def shortdate(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%-d %b %Y")


def month_label(m: str) -> str:
    return dt.date.fromisoformat(m + "-01").strftime("%b %Y")


# ---------------------------------------------------------------------------
# SVG charts — hand-built so the document is self-contained and prints
# ---------------------------------------------------------------------------

def _nice_ticks(lo, hi, n=5):
    span = hi - lo
    raw = span / max(n - 1, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if span / step <= n:
            break
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + step * 0.5:
        ticks.append(round(t, 10))
        t += step
    return ticks


def _fmt_k(x):
    sign = "−" if x < 0 else ""
    x = abs(x)
    if x >= 1000:
        return f"{sign}${x/1000:,.0f}k"
    return f"{sign}${x:,.0f}"


def _quarter_ticks(dates):
    out = []
    seen = set()
    for i, d in enumerate(dates):
        key = (d[:4], (int(d[5:7]) - 1) // 3)
        if key not in seen:
            seen.add(key)
            out.append((i, dt.date.fromisoformat(d).strftime("%b %Y")))
    return out


def _esc(s):
    return htmlmod.escape(str(s), quote=True)


def chart_growth(dates, pf, bm, *, warmup_end, live_start, bench_label):
    W, H = 720, 320
    L, R, T, B = 56, 96, 28, 34
    pw, ph = W - L - R, H - T - B
    lo = min(min(pf), min(bm)) * 0.98
    hi = max(max(pf), max(bm)) * 1.02
    ticks = _nice_ticks(lo, hi, 6)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    n = len(dates)
    xs = lambda i: L + pw * i / (n - 1)
    ys = lambda v: T + ph * (1 - (v - lo) / (hi - lo))
    path = lambda v: "M" + " L".join(f"{xs(i):.1f} {ys(x):.1f}" for i, x in enumerate(v))
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Growth of $100,000: strategy versus {bench_label} baseline">']
    # warm-up band
    wi = dates.index(warmup_end) if warmup_end in dates else 0
    if wi > 0:
        parts.append(f'<rect x="{L}" y="{T}" width="{xs(wi)-L:.1f}" height="{ph}" class="band"/>')
        parts.append(f'<text x="{L+6}" y="{T+ph-8}" class="band-label">Detector warm-up · overlay inactive</text>')
    for t in ticks:
        y = ys(t)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{L-8}" y="{y+3.5:.1f}" class="tick" text-anchor="end">{_fmt_k(t)}</text>')
    for i, lab in _quarter_ticks(dates):
        if i == 0:
            continue
        parts.append(f'<text x="{xs(i):.1f}" y="{T+ph+16}" class="tick" text-anchor="middle">{lab}</text>')
    # live marker
    if live_start in dates:
        li = dates.index(live_start)
        parts.append(f'<line x1="{xs(li):.1f}" y1="{T}" x2="{xs(li):.1f}" y2="{T+ph}" class="marker"/>')
        parts.append(f'<text x="{xs(li)-5:.1f}" y="{T+12}" class="band-label" text-anchor="end">Live record begins</text>')
    parts.append(f'<path d="{path(bm)}" class="line s2"/>')
    parts.append(f'<path d="{path(pf)}" class="line s1"/>')
    # end labels
    for v, cls, name in ((pf, "s1", "Strategy"), (bm, "s2", bench_label)):
        y = ys(v[-1])
        parts.append(f'<circle cx="{xs(n-1):.1f}" cy="{y:.1f}" r="4" class="dot {cls}"/>')
        parts.append(f'<text x="{xs(n-1)+9:.1f}" y="{y+3.5:.1f}" class="end-label">{money(v[-1])}</text>')
    # crosshair layer (screen only, driven by JS)
    parts.append(f'<g class="hover" data-l="{L}" data-pw="{pw}" data-t="{T}" data-ph="{ph}" data-lo="{lo}" data-hi="{hi}">'
                 f'<line class="xhair" x1="0" y1="{T}" x2="0" y2="{T+ph}" style="display:none"/>'
                 f'<circle class="xdot s1" r="4" style="display:none"/><circle class="xdot s2" r="4" style="display:none"/>'
                 f'<rect class="hit" x="{L}" y="{T}" width="{pw}" height="{ph}" fill="transparent"/></g>')
    parts.append("</svg>")
    return "\n".join(parts)


def chart_drawdown(dates, dd_s, dd_b, *, bench_label, trough_label, trough_index):
    W, H = 720, 200
    L, R, T, B = 56, 96, 14, 30
    pw, ph = W - L - R, H - T - B
    lo = min(min(dd_s), min(dd_b)) * 1.08
    ticks = [t for t in _nice_ticks(lo, 0, 5) if t <= 0]
    lo = min(lo, ticks[0])
    n = len(dates)
    xs = lambda i: L + pw * i / (n - 1)
    ys = lambda v: T + ph * (1 - (v - lo) / (0 - lo))
    path = lambda v: "M" + " L".join(f"{xs(i):.1f} {ys(x):.1f}" for i, x in enumerate(v))
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Drawdown from peak: strategy versus {bench_label}">']
    for t in ticks:
        y = ys(t)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" class="grid"/>')
        lab = "0%" if abs(t) < 1e-12 else f"−{abs(t)*100:.0f}%"
        parts.append(f'<text x="{L-8}" y="{y+3.5:.1f}" class="tick" text-anchor="end">{lab}</text>')
    for i, lab in _quarter_ticks(dates):
        if i == 0:
            continue
        parts.append(f'<text x="{xs(i):.1f}" y="{T+ph+16}" class="tick" text-anchor="middle">{lab}</text>')
    area = path(dd_s) + f" L{xs(n-1):.1f} {ys(0):.1f} L{xs(0):.1f} {ys(0):.1f} Z"
    parts.append(f'<path d="{area}" class="area s1"/>')
    parts.append(f'<path d="{path(dd_b)}" class="line s2"/>')
    parts.append(f'<path d="{path(dd_s)}" class="line s1"/>')
    ti = trough_index
    parts.append(f'<circle cx="{xs(ti):.1f}" cy="{ys(dd_s[ti]):.1f}" r="4" class="dot s1"/>')
    parts.append(f'<text x="{xs(ti)+8:.1f}" y="{ys(dd_s[ti])+4:.1f}" class="end-label">{_esc(trough_label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def chart_columns(labels, values, *, aria, value_fmt, label_every=3, annotate=3, height=220, y_is_pct=True, unit_suffix=""):
    """Positive/negative columns from a zero baseline (monthly excess, trade P&L)."""
    W, H = 720, height
    L, R, T, B = 56, 16, 16, 30
    pw, ph = W - L - R, H - T - B
    lo, hi = min(0, min(values)) * 1.15, max(0, max(values)) * 1.15
    ticks = _nice_ticks(lo, hi, 5)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    n = len(values)
    slot = pw / n
    bw = min(24, slot * 0.7)
    xs = lambda i: L + slot * i + (slot - bw) / 2
    ys = lambda v: T + ph * (1 - (v - lo) / (hi - lo))
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(aria)}">']
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    dec = 1 if (y_is_pct and step < 0.01) else 0
    for t in ticks:
        y = ys(t)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" class="{"grid zero" if abs(t) < 1e-12 else "grid"}"/>')
        if y_is_pct:
            lab = "0%" if abs(t) < 1e-12 else ("−" if t < 0 else "+") + f"{abs(t)*100:.{dec}f}%"
        else:
            lab = _fmt_k(t)
        parts.append(f'<text x="{L-8}" y="{y+3.5:.1f}" class="tick" text-anchor="end">{lab}</text>')
    y0 = ys(0)
    order = sorted(range(n), key=lambda i: -abs(values[i]))[:annotate]
    for i, v in enumerate(values):
        y = ys(v)
        top, hgt = (y, y0 - y) if v >= 0 else (y0, y - y0)
        r = min(4, hgt / 2) if hgt > 0 else 0
        x = xs(i)
        if v >= 0:
            d = (f"M{x:.1f} {y0:.1f} V{top+r:.1f} Q{x:.1f} {top:.1f} {x+r:.1f} {top:.1f} "
                 f"H{x+bw-r:.1f} Q{x+bw:.1f} {top:.1f} {x+bw:.1f} {top+r:.1f} V{y0:.1f} Z")
        else:
            bot = top + hgt
            d = (f"M{x:.1f} {y0:.1f} V{bot-r:.1f} Q{x:.1f} {bot:.1f} {x+r:.1f} {bot:.1f} "
                 f"H{x+bw-r:.1f} Q{x+bw:.1f} {bot:.1f} {x+bw:.1f} {bot-r:.1f} V{y0:.1f} Z")
        parts.append(f'<path d="{d}" class="bar {"pos" if v >= 0 else "neg"}"/>')
        if i in order:
            ly = (y - 5) if v >= 0 else (y + 11)
            anchor = "start" if x < L + 40 else ("end" if x + bw > L + pw - 40 else "middle")
            lx = x if anchor == "start" else (x + bw if anchor == "end" else x + bw / 2)
            parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="val" text-anchor="{anchor}">{_esc(value_fmt(v))}</text>')
    for i, lab in enumerate(labels):
        if lab and (label_every == 1 or i % label_every == 0):
            parts.append(f'<text x="{xs(i)+bw/2:.1f}" y="{T+ph+16}" class="tick" text-anchor="middle">{_esc(lab)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def chart_stacked(labels, a, b, *, aria, name_a, name_b, annotate_idx=None, annotate_text=""):
    W, H = 720, 220
    L, R, T, B = 40, 16, 18, 30
    pw, ph = W - L - R, H - T - B
    tot = [x + y for x, y in zip(a, b)]
    hi = max(tot) * 1.12
    ticks = _nice_ticks(0, hi, 5)
    hi = max(hi, ticks[-1])
    n = len(a)
    slot = pw / n
    bw = min(24, slot * 0.7)
    xs = lambda i: L + slot * i + (slot - bw) / 2
    ys = lambda v: T + ph * (1 - v / hi)
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(aria)}">']
    for t in ticks:
        y = ys(t)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{L-8}" y="{y+3.5:.1f}" class="tick" text-anchor="end">{t:.0f}</text>')
    for i in range(n):
        x = xs(i)
        ya, yb = ys(a[i]), ys(a[i] + b[i])
        if a[i] > 0:
            parts.append(f'<rect x="{x:.1f}" y="{ya:.1f}" width="{bw:.1f}" height="{ys(0)-ya:.1f}" class="bar s1"/>')
        if b[i] > 0:
            top = yb
            hgt = ya - yb - (2 if a[i] > 0 else 0)
            parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(hgt,0):.1f}" rx="3" class="bar muted"/>')
    for i, lab in enumerate(labels):
        if lab and i % 3 == 0:
            parts.append(f'<text x="{xs(i)+bw/2:.1f}" y="{T+ph+16}" class="tick" text-anchor="middle">{_esc(lab)}</text>')
    if annotate_idx is not None:
        x = xs(annotate_idx) + bw + 7
        y = ys(tot[annotate_idx]) + 4
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" class="val" text-anchor="start">{_esc(annotate_text)}</text>')
    # legend
    parts.append(f'<g class="legend" transform="translate({L},{6})">'
                 f'<rect x="0" y="0" width="10" height="10" class="bar s1"/><text x="14" y="9" class="tick">{_esc(name_a)}</text>'
                 f'<rect x="120" y="0" width="10" height="10" rx="2" class="bar muted"/><text x="134" y="9" class="tick">{_esc(name_b)}</text></g>')
    parts.append("</svg>")
    return "\n".join(parts)


def chart_hbars(items, *, aria, total):
    """Horizontal single-series bars: [(label, value)], value at the tip."""
    n = len(items)
    rowh = 22
    W = 720
    L, R, T, B = 170, 60, 6, 6
    H = T + B + rowh * n
    pw = W - L - R
    hi = max(v for _, v in items)
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(aria)}">']
    for i, (lab, v) in enumerate(items):
        y = T + rowh * i + 4
        w = pw * v / hi
        parts.append(f'<text x="{L-10}" y="{y+11}" class="tick" text-anchor="end">{_esc(lab)}</text>')
        parts.append(f'<path d="M{L} {y} H{L+w-4:.1f} Q{L+w:.1f} {y} {L+w:.1f} {y+4} V{y+10} Q{L+w:.1f} {y+14} {L+w-4:.1f} {y+14} H{L} Z" class="bar s1"/>')
        parts.append(f'<text x="{L+w+8:.1f}" y="{y+11}" class="val">{v} <tspan class="tick">({v/total*100:.0f}%)</tspan></text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_context() -> dict:
    docs_index = os.path.join(ROOT, "docs", "index.html")
    bt = load_backtest_from_dashboard(docs_index)
    curve, trades = bt["curve"], bt["trades"]
    signals = load_signals(os.path.join(ROOT, "data", "ledger", "signals.jsonl"))
    run = latest_run_summary(os.path.join(ROOT, "data", "history"))
    health = _read_json(os.path.join(ROOT, "data", "run_health.json"))
    alerts = _read_json(os.path.join(ROOT, "data", "alerts.json"))
    registry = cfg.TICKER_REGISTRY
    labels = cfg.CATEGORY_LABELS
    taglines = getattr(cfg, "CATEGORY_TAGLINES", {})

    capital = float(cfg.PORTFOLIO_CAPITAL)
    unit = float(cfg.BACKTEST_UNIT_DOLLARS)
    bench = curve.get("baseline_ticker", cfg.BACKTEST_BASELINE_TICKER)
    dates = curve["dates"]
    pf = [capital + e for e in curve["equity"]]
    bm = [capital + e for e in curve["bench_equity"]]

    # --- portfolio-level ---
    s_all, b_all = series_stats(pf, dates), series_stats(bm, dates)
    rel_all = relative_stats(s_all["returns"], b_all["returns"])
    first_signal_date = min(s["date"] for s in signals)
    first_entry = min(t["entry_date"] for t in trades)
    i0 = dates.index(first_entry)
    s_act, b_act = series_stats(pf[i0:], dates[i0:]), series_stats(bm[i0:], dates[i0:])
    rel_act = relative_stats(s_act["returns"], b_act["returns"])
    live_start = min((s["detected_at"] for s in signals if s.get("provenance") == "live"), default=None)
    live_i = dates.index(live_start) if live_start in dates else None
    if live_i is not None and live_i < len(dates) - 5:
        s_live, b_live = series_stats(pf[live_i:], dates[live_i:]), series_stats(bm[live_i:], dates[live_i:])
    else:
        s_live = b_live = None

    ms, mb = monthly_returns(dates, pf), monthly_returns(dates, bm)
    months = list(ms.keys())
    excess_m = [ms[m] - mb[m] for m in months]
    active_months = [m for m in months if m >= first_entry[:7]]
    n_beat = sum(1 for m in active_months if ms[m] - mb[m] > 1e-9)
    n_lag = sum(1 for m in active_months if ms[m] - mb[m] < -1e-9)
    cy_s, cy_b = calendar_years(dates, pf), calendar_years(dates, bm)

    dd_s = []
    peak = pf[0]
    for x in pf:
        peak = max(peak, x)
        dd_s.append(x / peak - 1)
    dd_b = []
    peak = bm[0]
    for x in bm:
        peak = max(peak, x)
        dd_b.append(x / peak - 1)
    trough_i = dates.index(s_all["max_dd"]["trough_date"])

    # --- trades ---
    buy_signals = [s for s in signals if s["signal"] == "BUY" and s["ticker"] != bench]
    match_trades_to_signals(trades, buy_signals)
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_t = [t for t in trades if t["status"] == "OPEN"]
    pnl = [t["dollar_gain"] for t in closed]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p < 0]
    realized = sum(pnl)
    unrealized = sum(t["dollar_gain"] for t in open_t)
    n_win_all = sum(1 for t in trades if t["dollar_gain"] > 0)
    for t in trades:
        cat = registry.get(t["ticker"], {}).get("category", "")
        t["category"] = labels.get(cat, cat)
        t["sector"] = registry.get(t["ticker"], {}).get("sector", "")
        t["n_methods"] = len([m for m in t["methods"].split(",") if m.strip()])
        t["hold_days"] = ((dt.date.fromisoformat(t["exit_date"]) - dt.date.fromisoformat(t["entry_date"])).days
                          if t["exit_date"] else None)
    hold_bars = None  # dashboard reports 22 trading days; calendar days computed here
    avg_hold_cal = st.mean(t["hold_days"] for t in closed if t["hold_days"] is not None)

    exit_reasons = []
    for reason, label in (("target hit", "Trend target reached"), ("time stop", "30-bar time stop"),
                          ("divest signal", "Bearish signal — divested"), ("still open", "Still open")):
        g = [t for t in trades if t["exit_reason"] == reason]
        if not g:
            continue
        p = [t["dollar_gain"] for t in g]
        exit_reasons.append({
            "label": label, "n": len(g), "n_win": sum(1 for x in p if x > 0),
            "win_rate": sum(1 for x in p if x > 0) / len(g), "avg": st.mean(p), "sum": sum(p),
            "avg_pct": st.mean(t["pct_change"] for t in g) / 100,
        })

    by_cat = collections.defaultdict(list)
    for t in trades:
        by_cat[t["category"]].append(t)
    cat_rows = []
    for c, g in sorted(by_cat.items(), key=lambda kv: -sum(t["dollar_gain"] for t in kv[1])):
        p = [t["dollar_gain"] for t in g]
        cat_rows.append({"label": c, "n": len(g), "n_win": sum(1 for x in p if x > 0),
                         "sum": sum(p), "avg": st.mean(p)})

    by_methods = []
    for k in (2, 3, 4):
        g = [t for t in closed if t["n_methods"] == k]
        if g:
            p = [t["dollar_gain"] for t in g]
            by_methods.append({"k": k, "n": len(g), "win_rate": sum(1 for x in p if x > 0) / len(g),
                               "avg": st.mean(p), "sum": sum(p)})

    top_w = sorted(closed, key=lambda t: -t["dollar_gain"])[:5]
    top_l = sorted(closed, key=lambda t: t["dollar_gain"])[:5]
    by_ticker = collections.defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append(t["dollar_gain"])

    live_trades = sorted([t for t in trades if t.get("provenance") == "live"], key=lambda t: t["entry_date"])
    live_pnl = sum(t["dollar_gain"] for t in live_trades)
    live_n_win = sum(1 for t in live_trades if t["dollar_gain"] > 0)

    # --- capacity ---
    buy_by_month = collections.Counter(s["date"][:7] for s in buy_signals)
    inv_by_month = collections.Counter((t.get("signal_date") or t["entry_date"])[:7] for t in trades)
    n_skipped = len(buy_signals) - len(trades)
    if bt["n_skipped_banner"] is not None:
        n_skipped = bt["n_skipped_banner"]
    cap_months = [m for m in months if m >= first_signal_date[:7]]
    cap_inv = [inv_by_month.get(m, 0) for m in cap_months]
    cap_skip = [max(buy_by_month.get(m, 0) - inv_by_month.get(m, 0), 0) for m in cap_months]
    peak_m = max(cap_months, key=lambda m: buy_by_month.get(m, 0))
    peak_i = cap_months.index(peak_m)

    # concurrency
    ev = []
    for t in trades:
        ev.append((t["entry_date"], 1))
        ev.append((t["exit_date"] or dates[-1], -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = mx = 0
    mx_date = None
    for d, x in ev:
        cur += x
        if cur > mx:
            mx, mx_date = cur, d

    # --- signals ---
    sig_by_type = collections.Counter(s["signal"] for s in signals)
    sig_by_prov = collections.Counter(s.get("provenance") for s in signals)
    dz = [s["rationale"].get("details", {}).get("dev_z") for s in buy_signals]
    dz = [x for x in dz if x is not None]
    dpct = [s["rationale"].get("details", {}).get("deviation_pct") for s in buy_signals]
    dpct = [x for x in dpct if x is not None]

    # --- universe ---
    sector_counts = collections.Counter(v["sector"] for v in registry.values())
    top_sectors = sector_counts.most_common(8)
    other = sum(sector_counts.values()) - sum(v for _, v in top_sectors)
    sector_items = [(k, v) for k, v in top_sectors] + ([("Other", other)] if other else [])
    cat_order = list(labels.keys())
    universe_cats = []
    for c in cat_order:
        members = [(k, v["name"]) for k, v in registry.items() if v["category"] == c]
        if not members:
            continue
        universe_cats.append({"label": labels[c], "tagline": taglines.get(c, ""), "n": len(members),
                              "members": members,
                              "examples": ", ".join(k for k, _ in members[:6])})
    funds = [k for k, v in registry.items() if v["is_fund"]]
    mutual_funds = [k for k in funds if len(k) == 5 and k.endswith("X")]

    # --- pro forma scaling illustration ---
    tiers = []
    for name, amount in (("Pilot", 250_000), ("Core", 500_000), ("Scale", 1_000_000)):
        k = amount / capital
        tiers.append({"name": name, "capital": amount, "slice": unit * k,
                      "final": pf[-1] * k, "bench_final": bm[-1] * k,
                      "excess": (pf[-1] - bm[-1]) * k, "max_dd_usd": s_all["max_dd"]["dollars"] * k})

    # --- narrative facts that must not be hard-coded in the template ---
    s_rec, b_rec = s_all["max_dd"]["recovery_date"], b_all["max_dd"]["recovery_date"]
    if s_rec and b_rec:
        lead = dates.index(b_rec) - dates.index(s_rec)
        recovery_note = ("on the same session as the index" if lead == 0 else
                         f"{abs(lead)} session{'s' if abs(lead) != 1 else ''} {'ahead of' if lead > 0 else 'behind'} the index")
    else:
        recovery_note = "while the index had not yet recovered" if s_rec else "and has not yet recovered its peak"
    mdd_diff = s_all["max_dd"]["pct"] - b_all["max_dd"]["pct"]
    mdd_compare = ("fractionally shallower than" if -0.01 <= mdd_diff < 0 else "shallower than" if mdd_diff < -0.01
                   else "in line with" if abs(mdd_diff) < 1e-9 else "fractionally deeper than" if mdd_diff <= 0.01 else "deeper than")
    dd_note = ("The overlay neither deepened nor materially shortened the index’s own drawdown."
               if abs(mdd_diff) <= 0.01 else
               f"The overlay {'deepened' if mdd_diff > 0 else 'reduced'} the index’s drawdown by {abs(mdd_diff) * 100:.1f} percentage points.")
    cohorts = collections.defaultdict(list)
    for t in trades:
        cohorts[t["entry_date"][:7]].append(t["dollar_gain"])
    cohort_sums = {m: sum(v) for m, v in cohorts.items()}
    best_cohort, worst_cohort = max(cohort_sums, key=cohort_sums.get), min(cohort_sums, key=cohort_sums.get)
    peak_cohort_sum = cohort_sums.get(peak_m)
    same_best_day = s_all["best_day_date"] == b_all["best_day_date"]
    divest_g = [t for t in trades if t["exit_reason"] == "divest signal"]
    ts_g = [t for t in trades if t["exit_reason"] == "time stop"]
    live_losers = [t for t in live_trades if t["dollar_gain"] < 0]
    if not live_losers:
        live_loss_note = "no live trade has closed at a loss"
    elif len(live_losers) == 1:
        live_loss_note = (f"the one losing trade was {'cut by a bearish divest signal rather than allowed to run' if live_losers[0]['exit_reason'] == 'divest signal' else 'closed by the ' + live_losers[0]['exit_reason']}")
    else:
        live_loss_note = f"the {len(live_losers)} losing trades were closed by " + ", ".join(sorted({t['exit_reason'] for t in live_losers}))
    n_mf_trades = sum(1 for t in trades if t["ticker"] in mutual_funds)

    generated_at = dt.datetime.now(dt.timezone.utc)
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = "n/a"

    warmup_end = first_signal_date

    ctx = {
        "generated_at": generated_at.strftime("%-d %B %Y"),
        "generated_iso": generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        "as_of": run["latest_bar_date"], "as_of_long": longdate(run["latest_bar_date"]),
        "run_date": run["run_date"], "model_version": run["model_version"],
        "commit": commit, "author": "Jacob E. Thomas, PhD", "house": "Results Generation",
        "bench": bench,
        "capital": money(capital), "unit": money(unit), "unit_pct": f"{unit / capital * 100:.0f}%",
        "cost_bps": f"{cfg.BACKTEST_COST_BPS_PER_SIDE:.0f}", "max_hold": cfg.BACKTEST_MAX_HOLD_TRADING_DAYS,
        "anchor": cfg.SIGNAL_START_DATE, "anchor_long": longdate(cfg.SIGNAL_START_DATE),
        "end_long": longdate(dates[-1]), "n_days": len(dates),
        "sensitivity": run["sensitivity"], "z_rev": cfg.SENSITIVITY_PRESETS[run["sensitivity"]]["z_threshold"],
        "materiality": cfg.TRADE_MIN_ABS_DEVIATION_PCT, "warmup": cfg.CAUSAL_WARMUP_BARS,
        "n_tickers": len(registry), "n_categories": len(universe_cats), "n_funds": len(funds),
        "mutual_funds": ", ".join(mutual_funds),
        "coverage": f"{health['coverage_pct']:.0f}%", "basis_breaks": ", ".join(sorted(health.get("price_basis_breaks", {}).keys())) or "none",
        "duration_min": f"{run['duration_seconds'] / 60:.1f}",
        "ledger_signals": f"{run['ledger_signal_rows']:,}", "ledger_anomalies": f"{run['ledger_anomaly_rows']:,}",
        "n_basis_breaks": len(health.get("price_basis_breaks", {})),
        "recovery_note": recovery_note, "mdd_compare": mdd_compare, "dd_note": dd_note,
        "best_cohort": month_label(best_cohort), "best_cohort_pnl": money(cohort_sums[best_cohort], signed=True), "best_cohort_n": len(cohorts[best_cohort]),
        "worst_cohort": month_label(worst_cohort), "worst_cohort_pnl": money(cohort_sums[worst_cohort], signed=True), "worst_cohort_n": len(cohorts[worst_cohort]),
        "peak_cohort_pnl": money(peak_cohort_sum, signed=True) if peak_cohort_sum is not None else "—",
        "peak_is_best_cohort": peak_m == best_cohort,
        "same_best_day": same_best_day,
        "divest_all_losses": bool(divest_g) and all(t["dollar_gain"] < 0 for t in divest_g),
        "divest_n": len(divest_g),
        "ts_n": len(ts_g), "ts_win_rate": f"{sum(1 for t in ts_g if t['dollar_gain'] > 0) / len(ts_g) * 100:.0f}%" if ts_g else "—",
        "ts_avg": money(st.mean(t["dollar_gain"] for t in ts_g), signed=True) if ts_g else "—",
        "live_loss_note": live_loss_note, "n_mf_trades": n_mf_trades,
        "observations": f"{run['total_observations']:,}",
        "first_signal": longdate(first_signal_date), "first_entry": longdate(first_entry),
        "live_start": live_start, "live_start_long": longdate(live_start) if live_start else "—",
        "n_live_signals": sig_by_prov.get("live", 0), "n_backfill_signals": sig_by_prov.get("backfill", 0),
        "sig_by_type": [(k, sig_by_type[k]) for k in ("BUY", "SELL", "LONG", "SHORT", "REDUCE", "WATCH") if k in sig_by_type],
        "n_signals": len(signals), "n_buy": len(buy_signals),
        "buy_dev_z": num(st.mean(dz), 1), "buy_dev_pct": pct(st.mean(dpct) / 100, decimals=1),
        # headline
        "final": money(pf[-1]), "bench_final": money(bm[-1]),
        "total_ret": pct(s_all["total"]), "bench_total": pct(b_all["total"]),
        "excess_pp": pp(s_all["total"] - b_all["total"]), "excess_usd": money(pf[-1] - bm[-1], signed=True),
        "total_gain": money(pf[-1] - capital, signed=True),
        "cagr": pct(s_all["cagr"], signed=False), "bench_cagr": pct(b_all["cagr"], signed=False),
        "sharpe": num(s_all["sharpe"]), "bench_sharpe": num(b_all["sharpe"]),
        "sortino": num(s_all["sortino"]), "bench_sortino": num(b_all["sortino"]),
        "vol": pct(s_all["vol"], signed=False), "bench_vol": pct(b_all["vol"], signed=False),
        "mdd": pct(-s_all["max_dd"]["pct"]), "bench_mdd": pct(-b_all["max_dd"]["pct"]),
        "mdd_usd": money(-s_all["max_dd"]["dollars"]),
        "mdd_peak": shortdate(s_all["max_dd"]["peak_date"]), "mdd_trough": shortdate(s_all["max_dd"]["trough_date"]),
        "mdd_recovery": shortdate(s_all["max_dd"]["recovery_date"]) if s_all["max_dd"]["recovery_date"] else "not yet",
        "mdd_days_recover": s_all["max_dd"]["days_to_recover"],
        "calmar": num(s_all["calmar"]), "bench_calmar": num(b_all["calmar"]),
        "best_day": pct(s_all["best_day"]), "best_day_date": shortdate(s_all["best_day_date"]),
        "worst_day": pct(s_all["worst_day"]), "worst_day_date": shortdate(s_all["worst_day_date"]),
        "bench_best_day": pct(b_all["best_day"]), "bench_worst_day": pct(b_all["worst_day"]),
        "beta": num(rel_all["beta"]), "corr": num(rel_all["corr"]), "te": pct(rel_all["tracking_error"], signed=False),
        "ir": num(rel_all["info_ratio"]), "alpha": pct(rel_all["alpha_ann"]),
        "up_capture": f"{rel_all['up_capture'] * 100:.0f}%", "down_capture": f"{rel_all['down_capture'] * 100:.0f}%",
        "years": num(s_all["years"], 2),
        # active period
        "act_total": pct(s_act["total"]), "act_bench_total": pct(b_act["total"]),
        "act_cagr": pct(s_act["cagr"], signed=False), "act_bench_cagr": pct(b_act["cagr"], signed=False),
        "act_sharpe": num(s_act["sharpe"]), "act_bench_sharpe": num(b_act["sharpe"]),
        "act_excess_pp": pp(s_act["total"] - b_act["total"]),
        "act_ir": num(rel_act["info_ratio"]), "act_te": pct(rel_act["tracking_error"], signed=False),
        # live period
        "live_total": pct(s_live["total"]) if s_live else "—", "live_bench_total": pct(b_live["total"]) if b_live else "—",
        "live_excess_pp": pp(s_live["total"] - b_live["total"]) if s_live else "—",
        "live_days": (len(dates) - live_i) if live_i is not None else 0,
        # months
        "n_months_active": len(active_months), "n_beat": n_beat, "n_lag": n_lag,
        "n_pos_months": sum(1 for m in active_months if ms[m] > 0), "bench_pos_months": sum(1 for m in active_months if mb[m] > 0),
        "best_month": month_label(max(ms, key=ms.get)), "best_month_ret": pct(max(ms.values())),
        "worst_month": month_label(min(ms, key=ms.get)), "worst_month_ret": pct(min(ms.values())),
        "best_excess_month": month_label(months[excess_m.index(max(excess_m))]), "best_excess": pp(max(excess_m)),
        "worst_excess_month": month_label(months[excess_m.index(min(excess_m))]), "worst_excess": pp(min(excess_m)),
        "monthly_rows": [{"m": month_label(m), "s": pct(ms[m]), "b": pct(mb[m]), "x": pp(ms[m] - mb[m]),
                          "s_neg": ms[m] < 0, "b_neg": mb[m] < 0, "x_neg": ms[m] - mb[m] < -1e-9, "x_zero": abs(ms[m] - mb[m]) < 1e-9,
                          "active": m >= first_entry[:7], "year": m[:4]} for m in months],
        "cy_rows": [{"year": a["year"] + (" (partial)" if a["partial"] else ""), "s": pct(a["ret"]), "b": pct(b["ret"]),
                     "x": pp(a["ret"] - b["ret"]), "x_neg": a["ret"] - b["ret"] < -1e-9,
                     "span": f"{shortdate(a['from'])} – {shortdate(a['to'])}"} for a, b in zip(cy_s, cy_b)],
        # trades
        "n_trades": len(trades), "n_closed": len(closed), "n_open": len(open_t), "n_win_all": n_win_all,
        "win_rate_all": f"{n_win_all / len(trades) * 100:.0f}%", "win_rate": f"{len(wins) / len(closed) * 100:.0f}%",
        "profit_factor": num(sum(wins) / -sum(losses)) if losses else "—",
        "avg_win": money(st.mean(wins), signed=True), "avg_loss": money(st.mean(losses), signed=True),
        "avg_trade": money(st.mean(pnl), signed=True), "median_trade": money(st.median(pnl), signed=True),
        "avg_trade_pct": pct(st.mean(t["pct_change"] for t in closed) / 100), "median_trade_pct": pct(st.median(t["pct_change"] for t in closed) / 100),
        "win_loss_ratio": num(st.mean(wins) / -st.mean(losses)) if losses else "—",
        "realized": money(realized, signed=True), "unrealized": money(unrealized, signed=True),
        "overlay_pnl": money(realized + unrealized, signed=True),
        "baseline_pnl": money((pf[-1] - capital) - (realized + unrealized), signed=True),
        "avg_hold_cal": f"{avg_hold_cal:.0f}", "n_tickers_traded": len(by_ticker),
        "max_concurrent": mx, "max_concurrent_date": shortdate(mx_date) if mx_date else "—",
        "exit_reasons": [{**r, "win_rate_s": f"{r['win_rate'] * 100:.0f}%", "avg_s": money(r["avg"], signed=True),
                          "sum_s": money(r["sum"], signed=True), "avg_pct_s": pct(r["avg_pct"]),
                          "neg": r["avg"] < 0} for r in exit_reasons],
        "cat_rows": [{**r, "sum_s": money(r["sum"], signed=True), "avg_s": money(r["avg"], signed=True),
                      "neg": r["sum"] < 0} for r in cat_rows],
        "by_methods": [{**r, "win_rate_s": f"{r['win_rate'] * 100:.0f}%", "avg_s": money(r["avg"], signed=True),
                        "sum_s": money(r["sum"], signed=True)} for r in by_methods],
        "top_w": [{"t": t, "pnl": money(t["dollar_gain"], signed=True), "pct": pct(t["pct_change"] / 100)} for t in top_w],
        "top_l": [{"t": t, "pnl": money(t["dollar_gain"], signed=True), "pct": pct(t["pct_change"] / 100)} for t in top_l],
        "live_trades": [{"t": t, "pnl": money(t["dollar_gain"], signed=True), "pct": pct(t["pct_change"] / 100),
                         "neg": t["dollar_gain"] < 0} for t in live_trades],
        "live_pnl": money(live_pnl, signed=True), "live_n": len(live_trades), "live_n_win": live_n_win,
        "live_n_closed": sum(1 for t in live_trades if t["status"] == "CLOSED"),
        "backfill_n": sum(1 for t in trades if t.get("provenance") == "backfill"),
        "backfill_pnl": money(sum(t["dollar_gain"] for t in trades if t.get("provenance") == "backfill"), signed=True),
        "open_positions": [{"t": t, "pnl": money(t["dollar_gain"], signed=True), "pct": pct(t["pct_change"] / 100)} for t in open_t],
        "ledger_rows": [{**t, "pnl_s": money(t["dollar_gain"], signed=True), "pct_s": pct(t["pct_change"] / 100),
                         "neg": t["dollar_gain"] < 0, "entry_s": f"${t['entry_price']:,.2f}", "exit_s": f"${t['exit_price']:,.2f}",
                         "exit_date_s": t["exit_date"] or "open", "prov": (t.get("provenance") or "")[:1].upper()}
                        for t in sorted(trades, key=lambda t: t["entry_date"])],
        # capacity
        "n_skipped": n_skipped, "skip_rate": f"{n_skipped / len(buy_signals) * 100:.0f}%",
        "peak_month": month_label(peak_m), "peak_month_signals": buy_by_month[peak_m], "peak_month_funded": inv_by_month.get(peak_m, 0),
        "tiers": [{**t, "capital_s": money(t["capital"]), "slice_s": money(t["slice"]), "final_s": money(t["final"]),
                   "bench_final_s": money(t["bench_final"]), "excess_s": money(t["excess"], signed=True),
                   "mdd_s": money(-t["max_dd_usd"])} for t in tiers],
        # universe
        "sector_items": sector_items, "universe_cats": universe_cats,
        # charts
        "chart_growth": chart_growth(dates, pf, bm, warmup_end=warmup_end, live_start=live_start, bench_label=bench),
        "chart_drawdown": chart_drawdown(dates, dd_s, dd_b, bench_label=bench,
                                         trough_label=f"{pct(dd_s[trough_i])} · {shortdate(dates[trough_i])}", trough_index=trough_i),
        "chart_monthly_excess": chart_columns(
            [month_label(m) if i % 3 == 0 else "" for i, m in enumerate(months)], excess_m,
            aria="Monthly excess return of the strategy over the baseline", value_fmt=lambda v: pp(v), label_every=1),
        "chart_trades": chart_columns(
            ["" for _ in trades], sorted([t["dollar_gain"] for t in trades], reverse=True),
            aria="Profit and loss of every funded trade, sorted", value_fmt=lambda v: money(v, signed=True),
            label_every=1, annotate=2, height=200, y_is_pct=False),
        "chart_capacity": chart_stacked([month_label(m) for m in cap_months], cap_inv, cap_skip,
                                        aria="BUY signals per month: funded versus skipped for lack of capital",
                                        name_a="Funded", name_b="Skipped — book fully deployed",
                                        annotate_idx=peak_i,
                                        annotate_text=f"{buy_by_month[peak_m]} signals · {inv_by_month.get(peak_m, 0)} funded"),
        "chart_sectors": chart_hbars(sector_items, aria="Universe composition by sector", total=len(registry)),
        "hover_data": json.dumps({"dates": dates, "pf": [round(x) for x in pf], "bm": [round(x) for x in bm], "bench": bench}),
    }

    return ctx


def render_html(ctx: dict, toc_pages: dict | None = None) -> str:
    env = Environment(loader=FileSystemLoader(HERE), autoescape=False, trim_blocks=True, lstrip_blocks=True)
    return env.get_template("template.html").render(toc_pages=toc_pages or {}, **ctx)


def _toc_pages_from_pdf(pdf_path: str) -> dict:
    """Locate each section's first page by the invisible §MARK§ tokens the
    template prints in section headings. Needs pypdf; returns {} without it."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("pypdf not installed — contents page left without page numbers")
        return {}
    ids = {"S01": "s1", "S02": "s2", "S03": "s3", "S04": "s4", "S05": "s5", "S06": "s6", "S07": "s7",
           "S08": "s8", "S09": "s9", "S10": "s10", "S11": "s11", "S12": "s12",
           "APPA": "appA", "APPB": "appB", "APPC": "appC", "APPD": "appD"}
    found: dict = {}
    reader = PdfReader(pdf_path)
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for tok, sid in ids.items():
            if sid not in found and f"§{tok}§" in text:
                found[sid] = i
    return found


def _render_pdf(html_path: str, pdf_path: str) -> None:
    subprocess.run(["node", os.path.join(HERE, "render_pdf.cjs"), html_path, pdf_path], check=True)


def build(pdf: bool = False) -> str:
    ctx = build_context()
    out_html = os.path.join(HERE, "The_Signal_Prospectus.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(ctx))
    print(f"wrote {out_html}")
    if pdf:
        out_pdf = os.path.join(HERE, "The_Signal_Prospectus.pdf")
        _render_pdf(out_html, out_pdf)                      # pass 1: discover pagination
        toc = _toc_pages_from_pdf(out_pdf)
        if toc:
            with open(out_html, "w", encoding="utf-8") as f:
                f.write(render_html(ctx, toc))
            _render_pdf(out_html, out_pdf)                  # pass 2: contents with page numbers
        print(f"wrote {out_pdf} (contents pages: {toc or 'n/a'})")
    return out_html


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", action="store_true", help="also render the PDF with headless Chromium (needs node + playwright)")
    args = ap.parse_args()
    build(pdf=args.pdf)
