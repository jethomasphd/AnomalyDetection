# Signal-Action Decision Tree — Email Click Anomaly Detection for Deliverability

**Adapted from the RG Anomaly Detection Suite Architecture**
**Jacob E. Thomas, PhD**

---

## The Core Translation

In your stock system, the two dimensions are **deviation magnitude** (how far price is from EWMA) and **momentum trajectory** (accelerating, decelerating, breakout). The signal tells you what to *trade*.

In email deliverability, the two dimensions become **click-rate deviation** (how far the observed click rate is from its EWMA baseline) and **trajectory** — but now there's a critical third dimension: **anomaly direction**. Drops and spikes in email click data have fundamentally asymmetric causes, and each maps to a different layer of the deliverability stack.

| Stock System | Email Deliverability System |
|---|---|
| Price | Click rate (clicks / delivered) |
| 20-day EWMA | Sender-reputation-weighted EWMA (per ISP or aggregate) |
| Trading signal | Deliverability action |
| Confidence (method agreement) | Confidence (method agreement) — identical logic |

---

## The Watchlist Equivalent

Instead of tickers, you monitor **signal streams**:

| Stream | Analogous to | Why |
|---|---|---|
| Aggregate click rate (all ISPs) | S&P 500 index | Baseline. If everything is anomalous, it's you, not one ISP. |
| Per-ISP click rate (Gmail, Outlook, Yahoo, etc.) | Individual stocks | Isolates ISP-specific reputation or policy changes. |
| Per-campaign click rate | Sector groupings | Isolates content/creative problems from infrastructure problems. |
| Per-IP/domain click rate | Individual holdings | Isolates sending infrastructure issues. |
| Bot-click ratio (if measurable) | Volatility index | Context signal — high bot activity distorts all other metrics. |

---

## The Decision Tree

```
                    ┌─────────────────────────────┐
                    │   ANOMALY DETECTED           │
                    │   (2+ methods OR >97.5th     │
                    │    percentile consensus)      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   WHICH DIRECTION?           │
                    └──┬───────────────────────┬──┘
                       │                       │
              ─────────▼─────────     ─────────▼─────────
              │  CLICK RATE DROP │     │ CLICK RATE SPIKE │
              │  (below EWMA)   │     │ (above EWMA)     │
              ─────────┬─────────     ─────────┬─────────
                       │                       │
                       ▼                       ▼
              [See DROP tree]          [See SPIKE tree]
```

---

### DROP Signals — "You're losing the inbox"

Click rate drops are the deliverability emergency. The trajectory tells you how to respond.

```
IF click rate is far below trend AND momentum is DECELERATING (drop slowing):
    → WARM          [Mean-reversion: reputation damage is stabilizing]
    
    Action: Reduce volume 40-60%. Shift sends to your most engaged 
    segments only. Re-engage sequence on the suppressed ISP(s). 
    Monitor for 3-5 send cycles before restoring volume.
    
    Rationale: The bleeding has stopped, but you're in a reputation 
    hole. Sending to engaged users rebuilds positive signal. Restoring 
    volume too early re-triggers the drop.

---

IF click rate is far below trend AND momentum is ACCELERATING (drop deepening):
    → THROTTLE      [Trend-following: active reputation collapse]
    
    Action: Immediately reduce volume 70-90% on affected ISP(s). 
    Halt sends to unengaged segments entirely. Check authentication 
    (SPF/DKIM/DMARC) and blocklist status. Escalate to deliverability 
    team or ESP support.
    
    Rationale: You are actively being penalized. Every additional send 
    to unengaged users accelerates the damage. This is the equivalent 
    of "SHORT" — the trend is working against you and momentum is 
    building. Stop feeding it.

---

IF click rate is far below trend AND trajectory is BREAKOUT (extreme drop):
    → PAUSE         [Circuit breaker: catastrophic event]
    
    Action: Pause all campaigns on the affected stream immediately. 
    Run full diagnostic: blocklist check (Spamhaus, Barracuda, 
    Invaluement), Google Postmaster Tools review, authentication 
    audit, complaint rate check. Do not resume until root cause is 
    identified.
    
    Rationale: This is REDUCE EXPOSURE adapted — a structural break. 
    Something fundamental changed: you hit a spam trap, got 
    blocklisted, an authentication record broke, or an ISP changed 
    policy. Volume reduction isn't enough; you need to stop and 
    diagnose.

---

IF Fourier AND Matrix Profile BOTH flag (structural regime change in click pattern):
    → INVESTIGATE   [Unprecedented pattern: external cause likely]
    
    Action: Check for ISP policy changes (Google, Microsoft 
    announcements), ESP platform issues, DNS/authentication changes, 
    or list hygiene failures. Cross-reference against industry news 
    and ESP status pages.
    
    Rationale: When both frequency-domain and novelty-detection methods 
    agree that the click pattern has never looked like this before, 
    the cause is almost certainly external to your campaigns. The 
    rhythm of engagement has structurally changed — not just dipped.
```

---

### SPIKE Signals — "Something is inflating your metrics"

Click rate spikes in email are almost never good news. Unlike stocks, a sudden surge in clicks usually indicates measurement contamination, not genuine engagement improvement.

```
IF click rate is far above trend AND momentum is DECELERATING (spike fading):
    → AUDIT         [Transient contamination: probably bot clicks]
    
    Action: Analyze click timing distribution (bot clicks cluster 
    within seconds of delivery). Check user-agent strings for known 
    security scanners (Barracuda, Mimecast, Proofpoint prefetch). 
    Filter contaminated data from engagement metrics before making 
    any segmentation decisions.
    
    Rationale: Security scanners at enterprise domains "click" every 
    link to check for malware. This inflates your click rate but 
    represents zero human engagement. If you segment based on this 
    data, you'll promote disengaged users into your "active" cohort 
    and poison your sender reputation over time.

---

IF click rate is far above trend AND momentum is ACCELERATING (spike growing):
    → QUARANTINE    [Escalating contamination or list attack]
    
    Action: Immediately quarantine the affected segment or campaign 
    from engagement-based decisioning. Investigate: (1) list bombing 
    attack (sudden subscriptions followed by complaint wave), 
    (2) link scanner deployment at a major recipient domain, 
    (3) compromised tracking domain generating false clicks. Flag 
    all click data from this period as unreliable.
    
    Rationale: An accelerating click spike that isn't accompanied by 
    proportional conversion/revenue lift is almost certainly 
    artificial. Using this data for segmentation or reporting will 
    compound errors downstream.

---

IF click rate is far above trend AND trajectory is BREAKOUT (extreme spike):
    → LOCKDOWN      [Circuit breaker: possible attack or system failure]
    
    Action: Freeze all automated engagement-based sends. Check for 
    list bombing (subscription spike → click spike → complaint wave 
    is the classic attack pattern). Verify tracking pixel/link 
    integrity. Review for compromised API keys or unauthorized sends.
    
    Rationale: Extreme click spikes that break all historical patterns 
    are either a system malfunction or a deliberate attack. Either 
    way, any automated system that uses click data to trigger actions 
    (re-engagement flows, winback campaigns, segmentation updates) 
    must be paused until the data is verified.
```

---

### WATCH Signal — "Anomaly detected, no clear direction"

```
IF anomaly is detected but click rate is within normal deviation range:
    → WATCH         [Monitor for follow-through]
    
    Action: No immediate action. Flag for the next send cycle. If the 
    anomaly resolves, archive. If it persists or develops directionality 
    across 2-3 subsequent sends, re-evaluate using the appropriate 
    DROP or SPIKE tree.
    
    Rationale: Identical logic to the stock system. Something 
    statistically unusual happened, but it hasn't manifested as a 
    directional problem yet.
```

---

## Signal Summary Table

| Signal | Color | Direction | Trajectory | Action | Urgency |
|---|---|---|---|---|---|
| **WARM** | Green | Drop | Decelerating | Reduce volume, send to engaged only | Hours |
| **THROTTLE** | Orange | Drop | Accelerating | Cut volume 70-90%, check auth | Immediate |
| **PAUSE** | Red | Drop | Breakout | Halt sends, full diagnostic | Immediate |
| **INVESTIGATE** | Purple | Drop | Structural (Fourier + MP) | Check ISP/ESP/DNS changes | Hours |
| **AUDIT** | Yellow | Spike | Decelerating | Filter bot clicks from data | Same day |
| **QUARANTINE** | Amber | Spike | Accelerating | Isolate segment, investigate source | Hours |
| **LOCKDOWN** | Red | Spike | Breakout | Freeze automated flows, verify systems | Immediate |
| **WATCH** | Blue | Ambiguous | Any | Monitor next 2-3 send cycles | Days |

---

## Method Weight Retuning for Email Data

Your stock system weights work for price data, but email click data has different signal characteristics:

| Method | Stock Weight | Email Weight | Rationale |
|---|---|---|---|
| **Ensemble** | 30% | 30% | Still the broadest coverage. Keep it. |
| **Matrix Profile** | 25% | 30% | ↑ More valuable in email. "Never-before-seen click pattern" almost always means an external event (ISP change, attack, bot deployment). Novelty detection is king here. |
| **EWMA** | 25% | 25% | Still the primary trajectory classifier. Unchanged. |
| **Fourier** | 20% | 15% | ↓ Email engagement has weaker cyclical structure than stock prices. Fourier still catches regime changes, but its base signal is noisier. |

---

## The Deliverability Stack — Diagnostic Hierarchy

When a DROP signal fires, investigate in this order (each layer can cause drops in the layers above it):

```
Layer 5:  CONTENT          ← Spam trigger words, image ratio, link density
Layer 4:  ENGAGEMENT       ← List fatigue, segment staleness, send frequency
Layer 3:  REPUTATION       ← Complaint rates, spam trap hits, blocklist status
Layer 2:  AUTHENTICATION   ← SPF, DKIM, DMARC alignment failures
Layer 1:  INFRASTRUCTURE   ← IP warming state, DNS records, ESP platform issues
```

**Rule of thumb:** If the anomaly is isolated to one campaign → start at Layer 5. If it spans multiple campaigns on one ISP → start at Layer 3. If it spans all ISPs → start at Layer 1.

---

## Confidence Mapping (Unchanged)

The multi-method consensus logic translates directly:

| Confidence | Methods Agreeing | Email Interpretation |
|---|---|---|
| **Strong** | 3-4 of 4 | Act now. Multiple independent detectors agree something real is happening. |
| **Moderate** | 2 of 4 | Elevated alert. Prepare to act if the next send cycle confirms. |
| **Developing** | 1 of 4 | Monitor. Single-method flags in email data have a higher false-positive rate than stock data due to send-volume variance. |

---

## Key Differences from Stock Application

1. **Asymmetric signals.** In stocks, up and down are morally neutral — both can be opportunities. In email, drops are emergencies and spikes are contamination. The decision tree branches on direction first, then trajectory.

2. **Cadence is irregular.** Stock prices arrive every trading day at market close. Email data arrives at send-time, which may be daily, weekly, or campaign-triggered. The EWMA span and Matrix Profile subsequence length need to be denominated in *send cycles*, not calendar days.

3. **Per-ISP decomposition is mandatory.** The "aggregate click rate" is like a market index — useful for context but not actionable. Gmail, Outlook, and Yahoo have independent reputation systems. An anomaly at one ISP can be masked in aggregate. Always run detection per-ISP in addition to aggregate.

4. **Bot contamination has no stock analog.** Security scanners that prefetch links create phantom engagement that can mask real deliverability problems. Any production system needs a bot-filtering layer upstream of the anomaly detection pipeline, or at minimum a bot-click ratio as a context signal.

5. **The feedback loop is tighter.** A bad stock trade costs money but doesn't change the stock's behavior. A bad email send — to the wrong segment, at the wrong time, during a reputation dip — actively makes the problem worse. This is why the DROP signals escalate to volume reduction so aggressively. Every send during a reputation crisis is either medicine or poison; there's no neutral.

---

*Adapted from the RG Anomaly Detection Suite — Jacob E. Thomas, PhD*
