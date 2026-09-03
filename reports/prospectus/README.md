# The Signal — investment prospectus

A regenerable, print-ready prospectus for THE SIGNAL, built entirely from the
files the daily pipeline commits. No number in the document is typed by hand.

```
reports/prospectus/
  build_prospectus.py         reads the ledger, run history, health report and the
                              rendered backtest; computes every statistic; renders
                              the HTML (and, with --pdf, the PDF)
  template.html               the document: design, narrative, tables, inline SVG charts
  render_pdf.cjs              headless-Chromium renderer (Letter, running footer,
                              page numbers)
  capacity_study.py           re-runs the production backtest at larger capital
                              levels — the condition precedent named in Section 8
  The_Signal_Prospectus.html  generated
  The_Signal_Prospectus.pdf   generated
```

## Regenerate

```bash
pip install -r requirements.txt            # jinja2 is already a project dependency
python reports/prospectus/build_prospectus.py          # HTML only
python reports/prospectus/build_prospectus.py --pdf    # + PDF (needs node + playwright)
```

The PDF renderer needs Node and the `playwright` package with a Chromium build
(`npm i -g playwright && npx playwright install chromium`, or set
`CHROMIUM_PATH` to an existing Chromium binary). Page numbers in the table of
contents are filled by a second rendering pass when `pypdf` is installed
(`pip install pypdf`); without it the contents page lists sections without
page numbers.

## Inputs

| File | Used for |
|---|---|
| `docs/index.html` | daily equity / benchmark / drawdown series and the trade ledger of the walk-forward backtest, exactly as the dashboard shows them |
| `data/ledger/signals.jsonl` | signal counts, provenance, the BUY-signal capacity analysis, signal-to-trade matching |
| `data/history/run_<date>.json` | latest run summary (observations, ledger counts, duration) |
| `data/run_health.json` | coverage, stale feeds, price-basis breaks |
| `data/alerts.json` | run block |
| `anomaly_detection/config.py` | universe registry, category labels, protocol parameters |

## Capacity study

Section 8 of the prospectus notes that the $100,000 book skipped a large share
of its own BUY signals for lack of capital. Before funding a larger book, run
the pipeline (which regenerates `data/detection_results.csv`) and then:

```bash
python -m anomaly_detection
python reports/prospectus/capacity_study.py --capital 250000 500000 1000000
```

It prints, and writes to `capacity_study.csv`, the backtest at each capital
level under both sizing policies (proportional slice vs. fixed $10,000 slice).
