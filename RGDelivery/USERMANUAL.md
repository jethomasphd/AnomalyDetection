# User Manual — Email Click Anomaly Detection for RG Deliverability

**Author:** Jacob E. Thomas, PhD | Results Generation

---

## Purpose

This system monitors email click data across sending domains in RG's email platform. It runs four independent anomaly detection algorithms against each domain's daily click time series, identifies statistically unusual behavior, and translates those anomalies into **actionable deliverability signals** — Warm, Throttle, Pause, Investigate, Audit, Quarantine, Lockdown, or Watch.

The goal is straightforward: surface the moments that matter. When a sending domain's click pattern collapses unexpectedly, when bot activity inflates engagement metrics, when an ISP policy change structurally alters how recipients interact with your mail — this system flags it, explains it in plain English, and tells you what to do about it.

The dashboard updates automatically via GitHub Actions whenever you upload a new `data.csv`, or you can run it locally at any time.

---

## Data Requirements

### Input File

The system reads from `data.csv` in the `RGDelivery/` directory. This is Gmail data broken down by sending domain, with one row per domain per day.

**Required columns:**

| Column | Description |
|--------|-------------|
| `Sending Domain` | The domain used to send email (e.g., `yayjobs.net`) |
| `Date` | The date of the observation (e.g., `2026-02-10`) |
| `Clicks` | Number of clicks recorded that day |
| `Sent` | Number of emails sent |
| `Delivered` | Number of emails delivered |
| `Opens` | Number of opens |
| `Unsubscribes` | Number of unsubscribes |
| `Complaints` | Number of spam complaints |
| `Blocks` | Number of blocks |
| `Hard Bounces` | Number of hard bounces |
| `Soft Bounces` | Number of soft bounces |

### Filtering

Before any analysis, the data is cleaned in two passes:

1. **Row-level filter:** Any row with `Sent < 5000` is dropped. Low-volume sends produce noisy click data that distorts anomaly detection.
2. **Domain-level filter:** A domain must have at least 30 days of data (after the row filter) and an average of at least 50 daily sends to be included in the analysis.

---

## Updating the Dashboard

### Option 1: Push to GitHub (automated)

1. Replace `RGDelivery/data.csv` with your new data file (same format, same columns)
2. Commit and push to the repository
3. GitHub Actions detects the change and runs the pipeline automatically (~2 minutes)
4. The dashboard and results files are committed back to the repo

### Option 2: Run locally

```bash
cd RGDelivery

# Install dependencies (first time only)
pip install -r requirements.txt

# Run with defaults
python -m email_anomaly

# Point to a different CSV file
python -m email_anomaly --data /path/to/new_data.csv

# Higher sensitivity
python -m email_anomaly --sensitivity high

# Analyze specific domains only
python -m email_anomaly --domains "yayjobs.net,aptena.com,slothjob.net"
```

Then open `docs/index.html` in your browser to view the dashboard.

### Option 3: Manual trigger on GitHub

1. Navigate to **Actions** > **Email Click Anomaly Detection**
2. Click **Run workflow**
3. Optionally select sensitivity or specify domains
4. Wait for the run to complete

---

## Reading the Dashboard

### Summary Statistics

The top of the dashboard shows four cards:

| Card | What it tells you |
|------|-------------------|
| **Domains Monitored** | How many sending domains qualified for analysis |
| **Anomalies Detected** | Total anomalous domain-days found across the full date range |
| **Actionable Signals** | The subset of anomalies with a clear deliverability recommendation |
| **Date Range** | How many days of data were analyzed |

### The Scoreboard

A horizontal bar chart ranks every domain by its recent anomaly score (5-day average). Domains that need attention are at the top, colored by severity:

- **Red** (>0.5) — High anomaly score, likely requires immediate action
- **Orange** (>0.35) — Elevated, should be reviewed
- **Amber** (>0.2) — Mild elevation, monitor
- **Blue** (<0.2) — Normal range

This answers: *"Which domains should I look at first?"*

### Deliverability Signals

This is the core output. Each row represents a detected anomaly translated into an action:

| Column | What it tells you |
|--------|-------------------|
| **Signal** | The recommended action — color-coded pill |
| **Confidence** | How many detection methods independently agree — Strong (3-4), Moderate (2), or Developing (1) |
| **Domain** | The sending domain where the anomaly was detected |
| **Date** | When the anomaly occurred |
| **Clicks** | The click count on that date |
| **Methods** | Visual dots showing how many of the 4 detection methods flagged this date |
| **What to do & why** | Plain-English explanation and recommended action |

---

## Signal Types

Signals are asymmetric — drops and spikes have fundamentally different causes and require different responses. The system branches on direction first, then trajectory.

### DROP Signals — "You're losing the inbox"

| Signal | Color | When it fires | What to do |
|--------|-------|---------------|------------|
| **Warm** | Green | Clicks far below trend, decline is decelerating (stabilizing) | Reduce volume 40-60%. Shift to most engaged segments only. Monitor 3-5 send cycles before restoring volume. |
| **Throttle** | Orange | Clicks far below trend, decline is accelerating (getting worse) | Cut volume 70-90% immediately. Halt sends to unengaged segments. Check SPF/DKIM/DMARC and blocklist status. Escalate to deliverability team. |
| **Pause** | Red | Clicks in extreme collapse (breakout trajectory) | Pause all campaigns immediately. Run full diagnostic: blocklist check, Google Postmaster review, authentication audit. Do not resume until root cause is identified. |
| **Investigate** | Purple | Fourier + Matrix Profile both flag structural regime change | Check for ISP policy changes, ESP platform issues, DNS/authentication changes. Cross-reference with industry news. The engagement rhythm has structurally shifted. |

### SPIKE Signals — "Something is inflating your metrics"

| Signal | Color | When it fires | What to do |
|--------|-------|---------------|------------|
| **Audit** | Yellow | Clicks far above trend, spike is decelerating (fading) | Analyze click timing for bot signatures. Check user-agent strings for security scanners (Barracuda, Mimecast, Proofpoint). Filter contaminated data before making segmentation decisions. |
| **Quarantine** | Amber | Clicks far above trend, spike is accelerating (growing) | Quarantine affected segment from engagement-based decisioning. Investigate list bombing, link scanner deployment, or compromised tracking domain. |
| **Lockdown** | Red | Clicks in extreme spike (breakout trajectory) | Freeze all automated engagement-based sends. Check for list bombing pattern. Verify tracking pixel/link integrity. Review for compromised API keys. |

### Ambiguous

| Signal | Color | When it fires | What to do |
|--------|-------|---------------|------------|
| **Watch** | Blue | Anomaly detected but clicks are within normal deviation range | No immediate action. Monitor next 2-3 send cycles. If the anomaly persists or develops directionality, re-evaluate. |

### Confidence Levels

| Confidence | Methods Agreeing | Interpretation |
|------------|------------------|----------------|
| **Strong** | 3-4 of 4 | Act now. Multiple independent detectors agree. |
| **Moderate** | 2 of 4 | Elevated alert. Prepare to act if the next send cycle confirms. |
| **Developing** | 1 of 4 | Monitor. Single-method flags have higher false-positive rates in email data. |

---

## Domain Deep Dive

Click any domain button in the dashboard to see its full analysis:

1. **Main chart** (top) — Click count line with the 20-day EWMA trend overlay. Color-coded circles mark anomaly dates directly on the click line. Below, a bar chart shows the consensus anomaly score over time.

2. **Method detail charts** (2x2 grid):
   - **Fourier Transform** — "Has the engagement rhythm changed?" Shows spectral divergence over time.
   - **Matrix Profile** — "Never-before-seen click pattern?" Shows nearest-neighbor distance (higher = more novel).
   - **Statistical Ensemble** — "Do independent tests agree?" Stacked area showing Z-score, seasonal, and Isolation Forest components.
   - **EWMA Trend** — "Is click momentum abnormal?" Clicks vs. EWMA on top, deviation percentage bars below.

---

## The Four Detection Methods

### 1. Fourier Transform — Frequency-Domain Structural Change

Every sending domain has a characteristic engagement "rhythm" driven by send cadence, day-of-week patterns, and seasonal effects. The Fourier Transform decomposes the click series into frequency components and measures whether the energy distribution has shifted from the historical baseline.

- **Window:** 30-day sliding window compared against full-history baseline
- **Metric:** Symmetric KL divergence between local and historical frequency spectra
- **Weight:** 15% (reduced from 20% in stock system — email has weaker cyclical structure)
- **Best at catching:** ISP policy changes, ESP platform issues, authentication failures

### 2. Matrix Profile (STUMPY) — Subsequence Novelty Detection

For every recent 7-day window of click activity, the algorithm asks: *"What is the most similar 7-day window in this domain's entire history?"* If even the best match is poor, the pattern is genuinely unprecedented.

- **Algorithm:** STUMPY (Scalable Time series Unsupervised Matrix Profile)
- **Subsequence length:** 7 days (one week of email data)
- **Weight:** 30% (increased from 25% — novelty detection is critical for email because "never-before-seen click pattern" almost always means an external event)
- **Best at catching:** Bot deployments, list bombing attacks, sudden ISP filtering, blocklisting

### 3. Statistical Ensemble — Three Independent Tests

| Component | Weight | What it measures |
|-----------|--------|------------------|
| Z-Score | 40% | How many standard deviations clicks are from the rolling 30-day mean |
| Seasonal Decomposition (STL) | 30% | Unexplained residual after removing trend and 7-day (weekly) seasonality |
| Isolation Forest | 30% | Multivariate outlier detection across click count, daily change, and 20-day volatility |

- **Weight:** 30%
- **Best at catching:** Statistical outliers, unusual combinations of click volume and volatility

### 4. EWMA Trend Analysis — Click Momentum

The 20-day Exponentially Weighted Moving Average creates a responsive trend line. The system measures deviation from trend and classifies the trajectory:

| Trajectory | What it means |
|------------|---------------|
| **Breakout** | Deviation exceeds 80% of historical range — extreme move |
| **Accelerating** | Deviation is increasing (slope > 0.02) — momentum building |
| **Decelerating** | Deviation is decreasing (slope < -0.02) — momentum fading |
| **Normal** | Deviation is stable |

- **Weight:** 25%
- **Key role:** Trajectory classification drives signal type. Decelerating drops → Warm. Accelerating drops → Throttle. Breakout drops → Pause.

---

## Consensus Scoring

The four method scores combine into a weighted consensus score:

```
consensus = 0.15 x fourier + 0.30 x matrix_profile + 0.30 x ensemble + 0.25 x ewma
```

A domain-day is flagged anomalous when:
- Two or more individual methods flag it, **OR**
- The consensus score exceeds the 97.5th percentile of its full historical distribution

---

## Deliverability Diagnostic Stack

When a DROP signal fires, investigate in this order (each layer can cause drops in the layers above it):

```
Layer 5:  CONTENT          ← Spam trigger words, image ratio, link density
Layer 4:  ENGAGEMENT       ← List fatigue, segment staleness, send frequency
Layer 3:  REPUTATION       ← Complaint rates, spam trap hits, blocklist status
Layer 2:  AUTHENTICATION   ← SPF, DKIM, DMARC alignment failures
Layer 1:  INFRASTRUCTURE   ← IP warming state, DNS records, ESP platform issues
```

**Rule of thumb:**
- Anomaly isolated to one campaign → start at Layer 5 (Content)
- Anomaly spans multiple campaigns on one ISP → start at Layer 3 (Reputation)
- Anomaly spans all ISPs → start at Layer 1 (Infrastructure)

---

## Output Files

| File | Description |
|------|-------------|
| `docs/index.html` | The interactive dashboard — open in any browser |
| `data/alerts.json` | Structured signal data in JSON format |
| `data/email_data.csv` | Feature-engineered click data (regenerated each run) |
| `data/detection_results.csv` | Full detection results with all method scores (regenerated each run) |

---

## Configuration Reference

All parameters live in `email_anomaly/config.py`:

| Parameter | Default | What it controls |
|-----------|---------|------------------|
| `DEFAULT_DATA_PATH` | `data.csv` | Path to the input CSV file |
| `MIN_DATA_POINTS` | 30 | Minimum days of data for a domain to qualify |
| `MIN_DAILY_SENDS` | 50 | Minimum average daily sends for a domain to qualify |
| `DEFAULT_SENSITIVITY` | medium | Detection threshold — low / medium / high |
| `METHOD_WEIGHTS` | MP 30%, Ensemble 30%, EWMA 25%, Fourier 15% | Consensus weighting |
| `EWMA_SPAN` | 20 | EWMA lookback in days |
| `MP_SUBSEQUENCE_LENGTH` | 7 | Matrix Profile window (one week) |
| `FOURIER_TOP_K` | 5 | Number of frequency components to track |
| `ENSEMBLE_WEIGHTS` | Z-Score 40%, Seasonal 30%, IForest 30% | Sub-method weights within ensemble |

Row-level filtering (`Sent < 5000` drop) is applied in `data_load.py` before any other processing.

### Sensitivity Presets

| Level | Percentile Threshold | Behavior |
|-------|---------------------|----------|
| **Low** | 99.5th | Only the most extreme anomalies. Fewer signals, highest confidence. |
| **Medium** | 97.5th | Balanced. The default for routine monitoring. |
| **High** | 95.0th | Sensitive. Catches early-stage signals. More noise, but earlier detection. |

---

## Key Differences from the Stock System

1. **Asymmetric signals.** In stocks, up and down are both opportunities. In email, drops are emergencies and spikes are contamination. The decision tree branches on direction first.

2. **No API — manual upload.** Data is not queryable in real time. You upload a new `data.csv` and the dashboard updates. GitHub Actions automates the re-run on push.

3. **Method weights retuned.** Matrix Profile is weighted 30% (up from 25%) because novelty detection is critical for email — unprecedented click patterns almost always mean an external event. Fourier is weighted 15% (down from 20%) because email has weaker cyclical structure than stock prices.

4. **Weekly seasonality.** Seasonal decomposition uses a 7-day period (email's weekly send cycle) instead of the stock system's 5-day trading week. Matrix Profile uses a 7-day subsequence length to match.

5. **The feedback loop is tighter.** A bad stock trade costs money but does not change the stock's behavior. A bad email send during a reputation dip actively makes the problem worse. This is why DROP signals escalate to volume reduction so aggressively.

---

## Architecture

```
    data.csv (manual upload)
          |
    [1. Load & Filter]
    (drop Sent < 5000, qualify domains)
          |
    [2. Compute Features]
    (click change, click rate, volatility, z-scores)
          |
    +-----+-----+-----+-----+
    |           |           |           |
[Fourier]  [Matrix    [Ensemble]   [EWMA]
           Profile]
    |           |           |           |
    +-----+-----+-----+-----+
          |
    [3. Consensus Scoring]
    (weighted average, 2+ method agreement)
          |
    [4. Signal Derivation]
    (direction + trajectory → Warm/Throttle/Pause/Audit/etc.)
          |
    +-----+-----+
    |                 |
[alerts.json]   [Dashboard HTML]
```

The pipeline runs in five stages and typically completes in about 2 minutes for ~240 qualifying domains.

---

*Results Generation — Jacob E. Thomas, PhD*
