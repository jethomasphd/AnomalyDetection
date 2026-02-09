# CPM Anomaly Detection Pipeline — Build Specification

**Author:** Jacob E. Thomas, PhD — Principal Investigator & Data Scientist, Results Generation  
**Purpose:** Complete specification + annotated code corpus for building a production-ready CPM anomaly detection system  
**Target:** Claude Code build prompt  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture & Pipeline Stages](#2-architecture--pipeline-stages)
3. [Configuration & Environment](#3-configuration--environment)
4. [Stage 1: Data Ingestion](#4-stage-1-data-ingestion)
5. [Stage 2: Data Cleaning & Formatting](#5-stage-2-data-cleaning--formatting)
6. [Stage 3: Pivot to Signal Matrix](#6-stage-3-pivot-to-signal-matrix)
7. [Stage 4: Signal Merge & GCS Sync](#7-stage-4-signal-merge--gcs-sync)
8. [Stage 5: Anomaly Detection Engine](#8-stage-5-anomaly-detection-engine)
9. [Stage 6: Alert Generation](#9-stage-6-alert-generation)
10. [Stage 7: Cloud Upload & Distribution](#10-stage-7-cloud-upload--distribution)
11. [Stage 8: Visualization & Dashboard](#11-stage-8-visualization--dashboard)
12. [Stage 9: Orchestration (main)](#12-stage-9-orchestration)
13. [Known Issues & Required Modifications](#13-known-issues--required-modifications)
14. [User Guide Reference](#14-user-guide-reference)
15. [Build Instructions for Claude Code](#15-build-instructions-for-claude-code)

---

## 1. System Overview

This system monitors **CPM (Cost Per Mille)** performance across recruitment marketing campaigns in **13 countries** (US, GB, CA, IT, NL, IN, ZA, AU, FR, DE, ES, BR, MX). It fetches daily CPM data from a ResGen API endpoint, merges it into a historical signal matrix stored in Google Cloud Storage, runs four complementary anomaly detection algorithms, generates structured alerts (JSON + markdown with country flag emojis), uploads results to GCS, and produces interactive Plotly HTML dashboards.

### Data Flow

```
ResGen API Endpoint
        │
        ▼
[Stage 1] Fetch JSON → Parse nested rendered_output → Write raw CSV
        │
        ▼
[Stage 2] Clean/format CSV → Standardize columns → Date-stamped CSV
        │
        ▼
[Stage 3] Pivot to wide format → Country_SourceType × Date matrix
        │
        ▼
[Stage 4] Fetch historical signal.csv from GCS → Merge new column → Re-upload
        │
        ▼
[Stage 5] Run 4 anomaly detection algorithms on each domain time series
        │
        ▼
[Stage 6] Generate alerts (custom markdown, JSON, optional OpenAI-enhanced)
        │
        ▼
[Stage 7] Upload alert.json to GCS → Trigger downstream Slack via Smarty template
        │
        ▼
[Stage 8] Generate interactive Plotly HTML dashboards (per-domain + summary)
```

### Domain Naming Convention

Domains follow `{COUNTRY_CODE}-{source_type}` format (e.g., `US-xml`, `GB-placement`, `BR-api`). The system parses these to extract country codes for flag emoji display in alerts.

### Source Types

- `xml` — XML job feed integrations
- `placement` — Placement-based job sources
- `api` — API-based job sources

---

## 2. Architecture & Pipeline Stages

### Current State (What Exists)

The code was developed iteratively in Google Colab as sequential notebook cells. It contains:
- Multiple `if __name__ == "__main__"` blocks (from separate cells)
- Duplicate imports across stages
- A `!pip install` shell command (notebook syntax)
- A hardcoded OpenAI API key (MUST be externalized)
- State tracking via local pickle files (needs GCS integration for persistence across environments)
- Separate execution of each stage (no unified orchestrator)

### Target State (What to Build)

A modular Python package with:
- Unified configuration via environment variables or config file
- A single orchestrator that runs the full pipeline or individual stages
- Proper error handling and logging (replace print statements)
- GCS-based state persistence for incremental processing
- No hardcoded secrets
- CLI interface with argparse for all operational modes

### Dependencies

```
numpy
pandas
matplotlib
seaborn
scipy
stumpy
statsmodels
scikit-learn
plotly
jinja2
requests
google-cloud-storage
```

---

## 3. Configuration & Environment

### ⚠️ MODIFICATION REQUIRED: Externalize all secrets and endpoints

The original code hardcodes the API endpoint URL and an OpenAI API key. The production version must load these from environment variables.

```python
# ============================================================================
# CONFIGURATION — All configurable values in one place
# ============================================================================
import os
from datetime import datetime

# --- API Endpoints ---
# ResGen template endpoint that returns nested JSON with CPM data
ENDPOINT_URL = os.getenv(
    "RG_CPM_ENDPOINT",
    "<YOUR_RESGEN_TEMPLATE_ENDPOINT_URL>"  # e.g., https://rg-chatgpt.k8s.prod.<domain>/rg-chatgpt/template/<uuid>/run
)

# Optional Bearer token for the ResGen endpoint
BEARER = os.getenv("RG_API_BEARER_TOKEN", "").strip() or None

# OpenAI API key for GPT-4o enhanced alerts (optional — falls back to custom format)
# ⚠️ SECURITY: NEVER hardcode this. Original had a hardcoded key (now revoked).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or None

# --- Google Cloud Storage ---
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET", "<YOUR_GCS_BUCKET>")
SIGNAL_GCS_PATH = "Anomaly Detection/signal.csv"
ALERT_GCS_PATH = "Anomaly Detection/alert.json"
SIGNAL_CSV_URL = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/Anomaly%20Detection/signal.csv"

# --- Local File Paths ---
LOCAL_SIGNAL_FILENAME = "signal.csv"
OUTPUT_CSV = "cpm_by_country.csv"

# --- Dataset Selection ---
# "data_set_recent" → today's data | "data_set_trailing" → yesterday's trailing aggregation
DATASET_KEY = os.getenv("DATASET_KEY", "data_set_trailing")

# --- Detection Parameters ---
TYPE_ORDER = ["xml", "placement", "api"]  # Fixed ordering for TYPE column in CSV output
DEFAULT_SENSITIVITY = "low"               # low | medium | high
DEFAULT_LOOKBACK_DAYS = 90                # Days of historical context for incremental mode

# --- Threshold Configuration ---
# Sensitivity presets: maps sensitivity level to (threshold_percentile, min_thresholds)
SENSITIVITY_PRESETS = {
    "low": {
        "percentile": 0.995,
        "min_thresholds": {"fourier": 0.5, "matrix_profile": 0.6, "custom": 0.7, "ewma": 0.6}
    },
    "medium": {
        "percentile": 0.99,
        "min_thresholds": {"fourier": 0.4, "matrix_profile": 0.5, "custom": 0.6, "ewma": 0.5}
    },
    "high": {
        "percentile": 0.975,
        "min_thresholds": {"fourier": 0.3, "matrix_profile": 0.4, "custom": 0.5, "ewma": 0.4}
    },
}
```

---

## 4. Stage 1: Data Ingestion

**Purpose:** Fetch the latest CPM data from the ResGen template endpoint, parse the nested JSON response, extract the chosen dataset, and write a tidy CSV.

**Input:** ResGen API endpoint (returns JSON with nested `rendered_output`)  
**Output:** `cpm_by_country.csv` with columns: DATE, COUNTRY, TYPE, CPM

### How the Endpoint Works

The endpoint returns a JSON structure:
```json
{
  "data": [
    {
      "id": 123,
      "rendered_output": "{\"data_set_recent\": {\"US\": {\"xml\": 1.23, \"placement\": 0.45, \"api\": 0.67}, ...}, \"data_set_trailing\": {...}}"
    }
  ]
}
```

- `rendered_output` is a JSON-encoded string inside JSON
- Contains two sub-datasets: `data_set_recent` (current day) and `data_set_trailing` (yesterday's trailing aggregation)
- Each sub-dataset maps country codes to source type CPM values

### Date Assignment Rule

- `data_set_recent` → DATE = today (America/Chicago timezone)
- `data_set_trailing` → DATE = yesterday (America/Chicago timezone)

### Working Code

```python
# ============================================================================
# STAGE 1: DATA INGESTION — Fetch CPM data from ResGen API
# ============================================================================

from __future__ import annotations
import csv
import json
import os
import sys
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def http_fetch_json(url: str, bearer: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch JSON from the ResGen endpoint.
    Attempts GET first, falls back to POST with empty body if GET fails.
    This dual-method approach handles the ResGen template API which may
    require POST for some configurations.
    """
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    # Attempt GET first
    try:
        req = Request(url=url, headers=headers, method="GET")
        with urlopen(req) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    except HTTPError as e:
        # POST fallback on common HTTP error codes
        if e.code in (400, 401, 403, 404, 405, 415, 500):
            try:
                req = Request(url=url, headers=headers, method="POST")
                with urlopen(req, data=b"") as resp:
                    raw = resp.read()
                return json.loads(raw.decode("utf-8"))
            except Exception as e2:
                raise RuntimeError(f"POST fallback failed: {e2}") from e
        else:
            raise RuntimeError(f"GET failed: HTTP {e.code} - {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Response was not valid JSON: {e}") from e


def select_latest_item_by_id(data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pick the item with the maximum numeric `id` from the data list.
    Falls back to last element if no items have numeric IDs.
    The ResGen API returns multiple historical runs; we want the most recent.
    """
    if not data_list:
        raise RuntimeError("The 'data' list is empty; nothing to select.")
    with_ids = [d for d in data_list if isinstance(d.get("id", None), (int, float))]
    if with_ids:
        return max(with_ids, key=lambda d: d["id"])
    return data_list[-1]


def parse_rendered_output(rendered_output_val: Any) -> Dict[str, Any]:
    """
    Normalize 'rendered_output' field.
    The field is typically a JSON-encoded string nested inside the outer JSON.
    Sometimes it's already parsed as a dict (depends on API version).
    """
    if isinstance(rendered_output_val, dict):
        return rendered_output_val
    if isinstance(rendered_output_val, str):
        return json.loads(rendered_output_val)
    raise RuntimeError(
        f"Unsupported 'rendered_output' type: {type(rendered_output_val)}. "
        "Expected str (JSON-encoded) or dict."
    )


def get_output_date(dataset_key: str) -> str:
    """
    Determine the DATE value for the output CSV based on which dataset is selected.
    Uses America/Chicago timezone (ResGen HQ).
    
    - data_set_recent   → today's date
    - data_set_trailing → yesterday's date
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Chicago")
        today_local = datetime.now(tz=tz).date()
    except Exception:
        # Fallback if zoneinfo unavailable (Python < 3.9)
        today_local = date.today()

    if dataset_key == "data_set_trailing":
        return (today_local - timedelta(days=1)).isoformat()
    return today_local.isoformat()


def flatten_dataset(
    dataset: Dict[str, Dict[str, Any]],
    output_date: str,
    type_order: Optional[List[str]] = None
) -> List[Tuple[str, str, str, str]]:
    """
    Convert the nested CPM structure into flat rows.
    
    Input structure:
        { "US": {"xml": 1.23, "placement": 0.45, "api": 0.67}, "GB": {...}, ... }
    
    Output rows:
        [(DATE, COUNTRY, TYPE, CPM), ...]
    
    CPM values formatted to 6 decimal places.
    Types are ordered per type_order list, with any extras sorted alphabetically.
    """
    rows: List[Tuple[str, str, str, str]] = []
    for country in sorted(dataset.keys()):
        inner = dataset[country] or {}
        # Determine iteration order for source types
        if type_order:
            types = [t for t in type_order if t in inner]
            extras = sorted([k for k in inner.keys() if k not in types])
            types.extend(extras)
        else:
            types = sorted(inner.keys())
        for t in types:
            val = inner.get(t, None)
            if val is None:
                continue
            try:
                cpm_str = f"{float(val):.6f}"
            except (TypeError, ValueError):
                continue
            rows.append((output_date, country, t, cpm_str))
    return rows


def write_csv(rows: List[Tuple[str, str, str, str]], out_path: str) -> None:
    """Write tidy CPM rows to CSV with header: DATE, COUNTRY, TYPE, CPM"""
    if os.path.dirname(out_path):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DATE", "COUNTRY", "TYPE", "CPM"])
        writer.writerows(rows)


def fetch_cpm_data(endpoint_url: str = ENDPOINT_URL,
                   dataset_key: str = DATASET_KEY,
                   output_csv: str = OUTPUT_CSV,
                   bearer: str = BEARER) -> str:
    """
    Full Stage 1 pipeline: fetch → parse → flatten → write CSV.
    Returns the output CSV path on success.
    """
    # 1) Fetch and parse top-level JSON
    payload = http_fetch_json(endpoint_url, bearer=bearer)

    # 2) Validate shape and select latest by id
    data_list = payload.get("data", None)
    if not isinstance(data_list, list):
        raise RuntimeError("Response JSON did not contain a 'data' list.")
    latest_item = select_latest_item_by_id(data_list)

    # 3) Extract and parse the nested JSON string in 'rendered_output'
    if "rendered_output" not in latest_item:
        raise RuntimeError("Latest item lacks 'rendered_output'.")
    rendered = parse_rendered_output(latest_item["rendered_output"])

    # 4) Determine DATE based on dataset key
    output_date = get_output_date(dataset_key)

    # 5) Extract the chosen dataset
    if dataset_key not in rendered:
        available = ", ".join(sorted(rendered.keys()))
        raise RuntimeError(f"'{dataset_key}' not found. Available keys: {available}")

    dataset_obj = rendered[dataset_key]
    if not isinstance(dataset_obj, dict):
        raise RuntimeError(f"'{dataset_key}' is not a dict; cannot flatten.")

    # 6) Flatten to tidy rows and write CSV
    rows = flatten_dataset(dataset_obj, output_date, type_order=TYPE_ORDER)
    if not rows:
        raise RuntimeError(f"No rows produced after flattening '{dataset_key}'.")

    write_csv(rows, output_csv)

    # 7) Summary
    unique_countries = sorted({r[1] for r in rows})
    print(f"[Stage 1] Wrote {len(rows)} rows to '{output_csv}'")
    print(f"  DATE: {output_date} ({'today' if dataset_key == 'data_set_recent' else 'yesterday'})")
    print(f"  DATASET: {dataset_key}")
    print(f"  COUNTRIES: {', '.join(unique_countries)}")

    return output_csv
```

---

## 5. Stage 2: Data Cleaning & Formatting

**Purpose:** Clean the raw CSV from Stage 1, standardize column names, strip currency formatting, and save with a date-stamped filename.

**Input:** `cpm_by_country.csv` from Stage 1  
**Output:** `{MMDDYY}.csv` (e.g., `020926.csv`)

```python
# ============================================================================
# STAGE 2: DATA CLEANING — Standardize and format raw CPM data
# ============================================================================

import pandas as pd
from datetime import datetime


def clean_cpm_data(input_csv: str = OUTPUT_CSV, base_date: datetime = None) -> str:
    """
    Clean the raw CPM CSV:
    1. Strip whitespace from column names
    2. Rename to standard schema (Date, Country, Impression.JobSourceType, CPM)
    3. Convert CPM from string (possibly "$1.01") to float rounded to 2 decimals
    4. Save with date-stamped filename
    
    Returns the output filename.
    """
    if base_date is None:
        base_date = datetime.today()

    df = pd.read_csv(input_csv)

    # Clean column names (trailing whitespace from CSV)
    df.columns = df.columns.str.strip()

    # Rename to standard schema used downstream
    df = df.rename(columns={
        'DATE': 'Date',
        'COUNTRY': 'Country',
        'TYPE': 'Impression.JobSourceType'
    })

    # Convert CPM — handle both numeric and currency-formatted strings like "$1.01"
    df['CPM'] = df['CPM'].replace(r'[\$,]', '', regex=True).astype(float).round(2)

    # Keep only the columns needed downstream
    df = df[['Date', 'Country', 'Impression.JobSourceType', 'CPM']]

    # Save with date-stamped filename
    today_str = base_date.strftime('%m%d%y')
    output_path = f"{today_str}.csv"
    df.to_csv(output_path, index=False)

    print(f"[Stage 2] Cleaned data saved to: {output_path}")
    print(f"  Shape: {df.shape}")
    return output_path
```

---

## 6. Stage 3: Pivot to Signal Matrix

**Purpose:** Transform the long-format cleaned CSV into a wide-format signal matrix where each row is a `Country_SourceType` combination and each column is a date.

**Input:** `{MMDDYY}.csv` from Stage 2  
**Output:** `signal{MMDDYY}.csv` — single-day column ready to merge into historical signal.csv

```python
# ============================================================================
# STAGE 3: PIVOT — Transform to wide-format signal matrix
# ============================================================================

import pandas as pd
import numpy as np
from datetime import datetime


def pivot_to_signal_matrix(input_csv: str, base_date: datetime = None) -> str:
    """
    Pivot cleaned CPM data from long format to wide format.
    
    Input (long):
        Date, Country, Impression.JobSourceType, CPM
        2025-02-08, US, xml, 1.23
    
    Output (wide):
        Country_SourceType, 2/8/2025
        US-xml, 1.23
    
    The wide format is what the anomaly detection engine consumes.
    Each column is a date, each row is a country-source combination (domain).
    """
    if base_date is None:
        base_date = datetime.today()

    df = pd.read_csv(input_csv)

    # Ensure CPM is numeric
    df['CPM'] = pd.to_numeric(df['CPM'], errors='coerce')

    print(f"[Stage 3] Input shape: {df.shape}")
    print(f"  Unique dates: {df['Date'].nunique()}")
    print(f"  Unique countries: {df['Country'].nunique()}")
    print(f"  Unique source types: {df['Impression.JobSourceType'].nunique()}")

    # Create the domain identifier: COUNTRY-SourceType
    df['Country_SourceType'] = df['Country'] + '-' + df['Impression.JobSourceType']

    # Pivot: rows = domains, columns = dates, values = CPM
    pivot_df = df.pivot(
        index='Country_SourceType',
        columns='Date',
        values='CPM'
    ).reset_index()

    # Sort date columns chronologically
    id_col = pivot_df.columns[0]
    date_cols = [col for col in pivot_df.columns if col != id_col]
    try:
        date_cols_sorted = sorted(date_cols, key=lambda x: pd.to_datetime(x))
        pivot_df = pivot_df[[id_col] + date_cols_sorted]
    except Exception:
        pass  # If date parsing fails, keep original order

    # Save
    today_str = base_date.strftime('%m%d%y')
    output_filename = f'signal{today_str}.csv'
    pivot_df.to_csv(output_filename, index=False)

    print(f"[Stage 3] Pivoted signal saved to: {output_filename}")
    print(f"  Domains: {pivot_df.shape[0]}, Date columns: {pivot_df.shape[1] - 1}")

    return output_filename
```

---

## 7. Stage 4: Signal Merge & GCS Sync

**Purpose:** Fetch the historical `signal.csv` from Google Cloud Storage, merge today's new column into it, standardize all date column formats, re-upload to GCS.

**Input:** `signal{MMDDYY}.csv` from Stage 3 + historical `signal.csv` from GCS  
**Output:** Updated `signal.csv` (local + GCS)

### Date Column Standardization

A critical detail: date columns must use `M/D/YYYY` format (no leading zeros) for consistency. The system normalizes `YYYY-MM-DD`, `MM/DD/YYYY` (with zeros), and `YYYY_MM_DD` formats.

### ⚠️ MODIFICATION REQUIRED: State persistence via GCS

The original uses local pickle files for state tracking. For production use across environments (Colab, Vertex AI, CI/CD), state should be stored in GCS alongside the signal data.

```python
# ============================================================================
# STAGE 4: SIGNAL MERGE — Merge daily update into historical signal.csv
# ============================================================================

import pandas as pd
import re
import os
import sys
import requests
from io import StringIO
from datetime import datetime

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("Warning: google-cloud-storage not installed. Upload disabled.")


def standardize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize all date column names to M/D/YYYY format (no leading zeros).
    This ensures consistency between:
    - API output dates (YYYY-MM-DD)
    - Existing signal.csv dates (M/D/YYYY)
    - Any other date format variations
    
    Only affects column NAMES, not cell values.
    """
    column_mapping = {}

    for col in df.columns:
        if col == 'Country_SourceType':
            continue

        # Pattern 1: YYYY-MM-DD → M/D/YYYY
        if re.match(r'^\d{4}-\d{2}-\d{2}$', col):
            try:
                date_obj = datetime.strptime(col, '%Y-%m-%d')
                new_col = f'{date_obj.month}/{date_obj.day}/{date_obj.year}'
                column_mapping[col] = new_col
            except ValueError:
                pass

        # Pattern 2: MM/DD/YYYY → strip leading zeros
        elif re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', col):
            try:
                parts = col.split('/')
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                new_col = f'{month}/{day}/{year}'
                if new_col != col:
                    column_mapping[col] = new_col
            except (ValueError, IndexError):
                pass

        # Pattern 3: YYYY_MM_DD → M/D/YYYY
        elif re.match(r'^\d{4}[-_]\d{2}[-_]\d{2}$', col):
            try:
                date_str = col.replace('_', '-')
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                new_col = f'{date_obj.month}/{date_obj.day}/{date_obj.year}'
                column_mapping[col] = new_col
            except ValueError:
                pass

    if column_mapping:
        df = df.rename(columns=column_mapping)
        print(f"  Standardized {len(column_mapping)} date columns")

    return df


def upload_to_gcs(source_file: str,
                  bucket_name: str = GCS_BUCKET_NAME,
                  destination_blob: str = SIGNAL_GCS_PATH) -> bool:
    """Upload a local file to Google Cloud Storage."""
    if not GCS_AVAILABLE:
        print("  GCS library not available. Cannot upload.")
        return False

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob)
        blob.upload_from_filename(source_file)
        print(f"  Uploaded {source_file} → gs://{bucket_name}/{destination_blob}")
        return True
    except Exception as e:
        print(f"  GCS upload failed: {e}")
        return False


def fetch_signal_from_url(url: str = SIGNAL_CSV_URL) -> pd.DataFrame:
    """
    Fetch historical signal.csv from GCS public URL.
    Falls back to requests library if pandas direct read fails.
    Standardizes date columns immediately after fetch.
    """
    try:
        signal_df = pd.read_csv(url)
        signal_df = standardize_date_columns(signal_df)
        return signal_df
    except Exception:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            signal_df = pd.read_csv(StringIO(response.text))
            signal_df = standardize_date_columns(signal_df)
            return signal_df
        except Exception as e:
            print(f"  Failed to fetch signal.csv: {e}")
            return None


def merge_daily_signal(new_signal_csv: str,
                       base_date: datetime = None,
                       dry_run: bool = False,
                       auto_upload: bool = True) -> bool:
    """
    Merge a single-day signal file into the historical signal.csv.
    
    Steps:
    1. Fetch historical signal.csv from GCS (or local fallback)
    2. If the new date column already exists, drop it (re-run safe)
    3. Merge on Country_SourceType (outer join to handle new domains)
    4. Standardize all date columns
    5. Save locally and upload to GCS
    
    Returns True on success.
    """
    if base_date is None:
        base_date = datetime.now()

    print(f"[Stage 4] Merging signal data for {base_date.strftime('%B %d, %Y')}")

    if not os.path.exists(new_signal_csv):
        print(f"  Error: {new_signal_csv} not found")
        return False

    # Fetch historical signal.csv from GCS
    signal_df = fetch_signal_from_url()

    if signal_df is None:
        # Fallback to local file
        if os.path.exists(LOCAL_SIGNAL_FILENAME):
            signal_df = pd.read_csv(LOCAL_SIGNAL_FILENAME)
            signal_df = standardize_date_columns(signal_df)
        else:
            print("  No historical signal.csv available (URL or local)")
            return False

    print(f"  Historical signal: {signal_df.shape}")

    # Load and standardize the new daily data
    signal_new = pd.read_csv(new_signal_csv)
    signal_new = standardize_date_columns(signal_new)

    # Get the new date column name
    date_columns = [col for col in signal_new.columns if col != 'Country_SourceType']
    if not date_columns:
        print("  Error: No date column in update file")
        return False

    new_date_col = date_columns[0]
    print(f"  New date column: {new_date_col}")

    # Drop existing column if re-running (idempotent merge)
    if new_date_col in signal_df.columns:
        print(f"  Column {new_date_col} already exists — replacing")
        signal_df = signal_df.drop(columns=[new_date_col])

    # Merge
    merged_df = pd.merge(signal_df, signal_new, on='Country_SourceType', how='outer')
    merged_df = standardize_date_columns(merged_df)

    print(f"  Merged shape: {merged_df.shape} ({merged_df.shape[1] - 1} date columns)")

    if dry_run:
        print("  [DRY RUN — no files modified]")
        return True

    # Backup and save
    if os.path.exists(LOCAL_SIGNAL_FILENAME):
        backup = f'signal_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        pd.read_csv(LOCAL_SIGNAL_FILENAME).to_csv(backup, index=False)

    merged_df.to_csv(LOCAL_SIGNAL_FILENAME, index=False)
    print(f"  Saved locally: {LOCAL_SIGNAL_FILENAME}")

    # Upload to GCS
    if auto_upload and GCS_AVAILABLE:
        upload_to_gcs(LOCAL_SIGNAL_FILENAME)

    return True
```

### Utility Functions (from original)

```python
def download_signal_only():
    """Download signal.csv from GCS without merging."""
    signal_df = fetch_signal_from_url()
    if signal_df is not None:
        signal_df.to_csv(LOCAL_SIGNAL_FILENAME, index=False)
        print(f"Downloaded signal.csv: {signal_df.shape}")
        return True
    return False


def upload_existing_file():
    """Upload existing local signal.csv to GCS."""
    if not os.path.exists(LOCAL_SIGNAL_FILENAME):
        print(f"{LOCAL_SIGNAL_FILENAME} not found")
        return False
    df = pd.read_csv(LOCAL_SIGNAL_FILENAME)
    df = standardize_date_columns(df)
    df.to_csv(LOCAL_SIGNAL_FILENAME, index=False)
    return upload_to_gcs(LOCAL_SIGNAL_FILENAME)


def fix_existing_signal_file():
    """Fix date format inconsistencies in existing signal.csv."""
    if not os.path.exists(LOCAL_SIGNAL_FILENAME):
        return False
    df = pd.read_csv(LOCAL_SIGNAL_FILENAME)
    backup = f'signal_backup_before_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    df.to_csv(backup, index=False)
    df_fixed = standardize_date_columns(df)
    df_fixed.to_csv(LOCAL_SIGNAL_FILENAME, index=False)
    return True
```

---

## 8. Stage 5: Anomaly Detection Engine

**Purpose:** Run four complementary anomaly detection algorithms on each domain's time series.

**Input:** `signal.csv` (wide-format matrix)  
**Output:** Per-domain anomaly DataFrames + visualization data

### Algorithm Overview

| Method | Technique | Strengths | Weight/Role |
|--------|-----------|-----------|-------------|
| Fourier Transform | Frequency band energy distribution changes across sliding windows | Detects pattern/cycle shifts, seasonal disruptions | Structural change detection |
| Matrix Profile | STUMPY-based nearest-neighbor distance for subsequences | Finds never-before-seen patterns | Novelty detection |
| Custom Ensemble | Z-score (40%) + Seasonal decomposition residuals (30%) + Isolation Forest (30%), squared | General-purpose statistical outlier detection | Composite anomaly scoring |
| EWMA Trend | Derivative + acceleration of exponentially weighted moving average, with trajectory streak tracking | Early trend detection, direction classification | Operational monitoring (primary business signal) |

### Core Detection Functions

```python
# ============================================================================
# STAGE 5: ANOMALY DETECTION ENGINE
# ============================================================================

import numpy as np
import pandas as pd
from scipy import signal as scipy_signal
from scipy.fft import fft, fftfreq
import stumpy
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.ensemble import IsolationForest
import warnings
import pickle
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')


# --- Data Loading & Preprocessing ---

def load_data_from_csv(file_path: str):
    """
    Load wide-format signal CSV.
    Returns: (DataFrame, domain_column_name, list_of_date_columns)
    
    Expected format:
        Country_SourceType, 1/1/2025, 1/2/2025, ...
        US-xml, 0.85, 0.92, ...
    """
    try:
        df = pd.read_csv(file_path)
        domain_col = df.columns[0]  # First column is the domain identifier
        date_cols = [col for col in df.columns if col != domain_col]

        # Validate date columns
        for col in date_cols:
            try:
                pd.to_datetime(col)
            except Exception:
                print(f"  Warning: '{col}' may not be a valid date")

        # Ensure numeric values
        for col in date_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        return df, domain_col, date_cols

    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None, None, None


def preprocess_domain_data(domain_data, domain_name: str, date_cols: list):
    """
    Prepare a single domain's time series for analysis.
    
    1. Converts wide-format row to time series DataFrame (time, signal)
    2. Removes NaN values
    3. Removes outliers beyond 3 standard deviations
    
    Returns: (df_original, df_filtered)
    Both have columns: time, signal
    """
    data_dict = {
        'time': pd.to_datetime(date_cols),
        'signal': domain_data.values
    }
    df = pd.DataFrame(data_dict)
    df['signal'] = pd.to_numeric(df['signal'], errors='coerce')
    df = df.dropna()
    df = df.sort_values('time')
    df_original = df.copy()

    if len(df) < 10:
        print(f"  {domain_name}: Not enough data points ({len(df)})")
        return df, df

    # 3-sigma outlier removal
    mean = df['signal'].mean()
    std = df['signal'].std()
    lower = mean - 3 * std
    upper = mean + 3 * std
    df_filtered = df[(df['signal'] >= lower) & (df['signal'] <= upper)]

    print(f"  {domain_name}: {len(df)} points, {len(df) - len(df_filtered)} outliers removed")
    return df_original, df_filtered


# --- State Management ---
# ⚠️ MODIFICATION REQUIRED: Migrate from local pickle to GCS-based state

def load_previous_state(output_dir: str, domain_name: str = None):
    """Load processing state from previous run (for incremental mode)."""
    if domain_name:
        state_path = os.path.join(output_dir, domain_name, f"{domain_name}_state.pkl")
    else:
        state_path = os.path.join(output_dir, "anomaly_detection_state.pkl")

    if os.path.exists(state_path):
        try:
            with open(state_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"  Error loading state: {e}")
    return None


def save_current_state(state: dict, output_dir: str, domain_name: str = None):
    """Save processing state for future incremental runs."""
    if domain_name:
        domain_dir = os.path.join(output_dir, domain_name)
        os.makedirs(domain_dir, exist_ok=True)
        state_path = os.path.join(domain_dir, f"{domain_name}_state.pkl")
    else:
        os.makedirs(output_dir, exist_ok=True)
        state_path = os.path.join(output_dir, "anomaly_detection_state.pkl")

    try:
        with open(state_path, 'wb') as f:
            pickle.dump(state, f)
    except Exception as e:
        print(f"  Error saving state: {e}")


def get_relevant_timeframe(df, previous_state=None, lookback_days=90, incremental=True):
    """
    For incremental mode: return only the relevant time window
    (new data since last run + lookback period for context).
    """
    if not pd.api.types.is_datetime64_any_dtype(df['time']):
        df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')
    last_date = df['time'].max()

    if incremental and previous_state and 'last_date' in previous_state:
        last_processed = previous_state['last_date']
        if isinstance(last_processed, str):
            last_processed = pd.to_datetime(last_processed)
        lookback_date = last_date - timedelta(days=lookback_days)
        start_date = min(last_processed, lookback_date)
        return df[df['time'] >= start_date].copy(), last_date
    else:
        return df.copy(), last_date


# --- Method 1: Fourier Transform Analysis ---

def fourier_analysis(df, window_size=30, step_size=7):
    """
    Sliding-window Fourier analysis detecting frequency distribution changes.
    
    For each window:
    1. Detrend the signal
    2. Compute FFT
    3. Calculate energy in 4 frequency bands
    4. Track inter-window changes in band distribution
    5. Normalize anomaly scores to [0, 1]
    
    Returns DataFrame with columns:
        start_time, end_time, mid_time, total_energy,
        very_low, low, high, very_high (band energy proportions),
        freq_anomaly_score
    """
    bands = {
        'very_low': (0, 0.1),
        'low': (0.1, 0.2),
        'high': (0.2, 0.3),
        'very_high': (0.3, 0.5)
    }

    clean_df = df.copy()
    clean_df['signal'] = pd.to_numeric(clean_df['signal'], errors='coerce')
    clean_df = clean_df.dropna(subset=['signal']).reset_index(drop=True)

    if len(clean_df) < window_size:
        return pd.DataFrame()

    times = clean_df['time'].values
    values = clean_df['signal'].values
    results = []

    for i in range(0, len(clean_df) - window_size, step_size):
        window_times = times[i:i+window_size]
        window_values = values[i:i+window_size]

        detrended = scipy_signal.detrend(window_values)
        fft_values = fft(detrended)
        fft_freqs = fftfreq(len(detrended), 1)

        pos_mask = fft_freqs > 0
        freqs = fft_freqs[pos_mask]
        amplitudes = np.abs(fft_values[pos_mask])

        total_energy = np.sum(amplitudes**2)
        band_energy = {}
        for band_name, (low_freq, high_freq) in bands.items():
            mask = (freqs >= low_freq) & (freqs < high_freq)
            energy = np.sum(amplitudes[mask]**2)
            band_energy[band_name] = energy / total_energy if total_energy > 0 else 0

        result = {
            'start_time': window_times[0],
            'end_time': window_times[-1],
            'mid_time': window_times[window_size // 2],
            'total_energy': total_energy
        }
        result.update(band_energy)
        results.append(result)

    results_df = pd.DataFrame(results)
    if results_df.empty:
        return results_df

    # Calculate inter-window band distribution changes
    for band in bands:
        results_df[f'{band}_change'] = results_df[band].diff().abs()

    band_changes = [f'{band}_change' for band in bands]
    results_df['freq_anomaly_score'] = results_df[band_changes].sum(axis=1)

    # Normalize to [0, 1]
    max_score = results_df['freq_anomaly_score'].max()
    if max_score > 0:
        results_df['freq_anomaly_score'] = results_df['freq_anomaly_score'] / max_score

    return results_df


# --- Method 2: Matrix Profile ---

def matrix_profile_analysis(df, window_size=7):
    """
    STUMPY-based matrix profile analysis for novelty detection.
    
    High matrix profile values indicate subsequences that are dissimilar
    to all other subsequences — i.e., never-before-seen patterns.
    
    Returns DataFrame with columns: time, matrix_profile, mp_anomaly_score
    """
    try:
        ts = pd.to_numeric(df['signal'], errors='coerce').dropna().values

        if len(ts) < window_size * 2:
            return pd.DataFrame()

        valid_indices = pd.to_numeric(df['signal'], errors='coerce').notna()
        valid_times = df['time'][valid_indices].reset_index(drop=True)

        matrix_profile = stumpy.stump(ts, window_size)

        mp_df = pd.DataFrame({
            'time': valid_times.values[window_size-1:len(ts)],
            'matrix_profile': matrix_profile[:, 0]
        })

        max_mp = mp_df['matrix_profile'].max()
        mp_df['mp_anomaly_score'] = mp_df['matrix_profile'] / max_mp if max_mp > 0 else 0

        return mp_df
    except Exception as e:
        print(f"  Matrix Profile error: {e}")
        return pd.DataFrame()


# --- Method 3: Custom Ensemble ---

def custom_anomaly_detection(df, window_size=14, sensitivity_factor=0.7):
    """
    Composite anomaly detection combining:
    - Rolling Z-score (40% weight)
    - Seasonal decomposition residuals (30% weight)
    - Isolation Forest outlier detection (30% weight)
    
    Final score is squared for better separation of true anomalies.
    
    Returns DataFrame with columns: time, signal, custom_anomaly_score
    """
    clean_df = df.copy()
    clean_df['signal'] = pd.to_numeric(clean_df['signal'], errors='coerce')
    clean_df = clean_df.dropna(subset=['signal']).reset_index(drop=True)

    if len(clean_df) < window_size * 2:
        return pd.DataFrame()

    result_df = clean_df.copy()

    # Component 1: Rolling Z-score
    result_df['rolling_mean'] = clean_df['signal'].rolling(window=window_size).mean()
    result_df['rolling_std'] = clean_df['signal'].rolling(window=window_size).std()
    result_df['z_score'] = ((clean_df['signal'] - result_df['rolling_mean']) /
                            result_df['rolling_std']).abs().fillna(0)

    # Component 2: Seasonal decomposition residuals
    if len(clean_df) >= 2 * window_size:
        try:
            decomp = seasonal_decompose(clean_df['signal'], model='additive', period=window_size)
            result_df['residual'] = decomp.resid.abs().fillna(0)
        except Exception:
            result_df['residual'] = 0
    else:
        result_df['residual'] = 0

    # Component 3: Isolation Forest
    features = np.array(clean_df['signal']).reshape(-1, 1)
    try:
        iso_forest = IsolationForest(contamination=0.01, random_state=42)
        result_df['isolation_forest'] = (iso_forest.fit_predict(features) == -1).astype(int)
    except Exception:
        result_df['isolation_forest'] = 0

    # Normalize components
    max_z = result_df['z_score'].max()
    result_df['z_score_norm'] = result_df['z_score'] / max_z if max_z > 0 else 0
    max_r = result_df['residual'].max()
    result_df['residual_norm'] = result_df['residual'] / max_r if max_r > 0 else 0

    # Weighted composite score, squared for separation
    result_df['custom_anomaly_score'] = (
        0.4 * result_df['z_score_norm'] +
        0.3 * result_df['residual_norm'] +
        0.3 * result_df['isolation_forest']
    ) * sensitivity_factor

    result_df['custom_anomaly_score'] = result_df['custom_anomaly_score'] ** 2

    return result_df[['time', 'signal', 'custom_anomaly_score']]


# --- Method 4: EWMA Trend Analysis ---

def ewma_analysis(df, span=7, threshold_multiplier=2.0):
    """
    EWMA-based trend detection — the primary business signal.
    
    Process:
    1. Calculate EWMA of the signal
    2. Compute first derivative (rate of change) and acceleration
    3. Classify trajectory: increasing / decreasing / stable
    4. Track consecutive-day streaks of same trajectory
    5. Amplify anomaly scores for longer increasing streaks (log scaling)
    
    Returns DataFrame with columns:
        time, signal, ewma, ewma_derivative, ewma_acceleration,
        ewma_anomaly_score, trajectory, trajectory_streak
    """
    clean_df = df.copy()
    clean_df['signal'] = pd.to_numeric(clean_df['signal'], errors='coerce')
    clean_df = clean_df.dropna(subset=['signal']).reset_index(drop=True)

    if len(clean_df) < span * 2:
        return pd.DataFrame()

    # EWMA and derivatives
    clean_df['ewma'] = clean_df['signal'].ewm(span=span).mean()
    clean_df['ewma_derivative'] = clean_df['ewma'].diff().fillna(0)
    clean_df['ewma_acceleration'] = clean_df['ewma_derivative'].diff().fillna(0)

    derivative_std = clean_df['ewma_derivative'].std()

    if derivative_std > 0:
        # Positive trend scoring (upward movement beyond threshold)
        clean_df['positive_trend'] = (
            clean_df['ewma_derivative'] > threshold_multiplier * derivative_std).astype(float)
        clean_df['trend_magnitude'] = (
            clean_df['ewma_derivative'] / (threshold_multiplier * derivative_std)).clip(lower=0)
        clean_df['ewma_anomaly_score'] = clean_df['positive_trend'] * clean_df['trend_magnitude']

        max_score = clean_df['ewma_anomaly_score'].max()
        if max_score > 0:
            clean_df['ewma_anomaly_score'] = clean_df['ewma_anomaly_score'] / max_score
    else:
        clean_df['ewma_anomaly_score'] = 0

    # Trajectory classification
    clean_df['trajectory'] = np.select(
        [
            clean_df['ewma_derivative'] > threshold_multiplier * derivative_std,
            clean_df['ewma_derivative'] < -threshold_multiplier * derivative_std,
        ],
        ['increasing', 'decreasing'],
        default='stable'
    )

    # Streak counting (consecutive days with same trajectory)
    clean_df['trajectory_streak'] = 0
    streak = 0
    current = None
    for i, row in clean_df.iterrows():
        if row['trajectory'] == current:
            streak += 1
        else:
            streak = 1
            current = row['trajectory']
        clean_df.at[i, 'trajectory_streak'] = streak

    # Amplify scores for longer increasing streaks (log scaling)
    inc_mask = clean_df['trajectory'] == 'increasing'
    if inc_mask.sum() > 0:
        clean_df.loc[inc_mask, 'ewma_anomaly_score'] = (
            clean_df.loc[inc_mask, 'ewma_anomaly_score'] *
            np.log1p(clean_df.loc[inc_mask, 'trajectory_streak']) / np.log1p(1)
        )

    clean_df['ewma_anomaly_score'] = clean_df['ewma_anomaly_score'].clip(0, 1)

    return clean_df[['time', 'signal', 'ewma', 'ewma_derivative',
                      'ewma_acceleration', 'ewma_anomaly_score', 'trajectory',
                      'trajectory_streak']].copy()
```

---

## 9. Stage 6: Alert Generation

**Purpose:** Generate structured alerts in multiple formats from the anomaly detection results.

### Alert Formats

1. **Custom Markdown** — Formatted with country flag emojis, grouped by detection method
2. **JSON** — Structured format for downstream integration (Smarty template → Slack)
3. **OpenAI GPT-4o Enhanced** — Optional natural language summarization (falls back to custom on failure)

```python
# ============================================================================
# STAGE 6: ALERT GENERATION
# ============================================================================

import json
import requests


def get_country_flag(country_code: str) -> str:
    """Map 2-letter country codes to flag emojis."""
    flags = {
        'US': '🇺🇸', 'GB': '🇬🇧', 'UK': '🇬🇧', 'BR': '🇧🇷', 'CA': '🇨🇦',
        'AU': '🇦🇺', 'IN': '🇮🇳', 'MX': '🇲🇽', 'NL': '🇳🇱', 'DE': '🇩🇪',
        'FR': '🇫🇷', 'IT': '🇮🇹', 'ES': '🇪🇸', 'ZA': '🇿🇦',
        'JP': '🇯🇵', 'CN': '🇨🇳', 'KR': '🇰🇷', 'SE': '🇸🇪',
    }
    return flags.get(country_code.upper(), '🌐')


def parse_domain_name(domain_name: str) -> tuple:
    """
    Extract country code and service from domain name.
    Expected format: XX-service (e.g., US-xml, GB-placement)
    """
    if '-' in domain_name:
        parts = domain_name.split('-', 1)
    elif '_' in domain_name:
        parts = domain_name.split('_', 1)
    else:
        parts = [domain_name[:2], domain_name[2:] or 'service']
    return parts[0] if parts else 'XX', parts[1] if len(parts) > 1 else 'service'


def generate_custom_alert(all_domain_anomalies: dict, alert_date,
                          incremental=False, previous_state=None) -> str:
    """
    Generate a markdown-formatted alert with flag emojis, grouped by method.
    
    Output format:
        **CPM Anomaly Detection Alert**
        **Date:** MM/DD/YYYY
        
        **Matrix Profile Anomalies**
        *(Unusual subsequences detected — may forecast significant spikes or dips)*
        • 🇺🇸 **US-xml**
        
        **Increasing EWMA Trend Anomalies**
        *(Significant upward trajectory)*
        • 🇧🇷 **BR-xml** — **5 days** upward trend
    """
    date_str = f"{alert_date.month:02d}/{alert_date.day:02d}/{alert_date.year}"

    # Collect anomalies by method type
    buckets = {
        'matrix_profile': [], 'fourier': [], 'custom': [],
        'ewma_increasing': [], 'ewma_decreasing': []
    }

    for domain_name, anomalies_df in all_domain_anomalies.items():
        if anomalies_df.empty:
            continue

        country_code, service = parse_domain_name(domain_name)
        flag = get_country_flag(country_code)

        # Filter for relevant time window
        if incremental and previous_state and 'last_date' in previous_state:
            relevant = anomalies_df[anomalies_df['time'] > previous_state['last_date']]
        else:
            relevant = anomalies_df[anomalies_df['date'] == alert_date.date()]

        if relevant.empty:
            continue

        for _, anomaly in relevant.iterrows():
            atype = anomaly['type']
            label = f"• {flag} **{country_code}-{service}**"

            if atype == 'Matrix Profile':
                buckets['matrix_profile'].append(label)
            elif atype == 'Fourier Analysis':
                buckets['fourier'].append(label)
            elif atype == 'Custom':
                buckets['custom'].append(label)
            elif atype == 'EWMA Trend':
                direction = anomaly.get('direction', '')
                # Extract streak duration from details string
                details = anomaly.get('details', '')
                days = '1'
                if 'trajectory for' in details:
                    try:
                        days = details.split('trajectory for ')[1].split(' days')[0]
                    except IndexError:
                        pass
                duration = f"{days} day" if days == '1' else f"{days} days"
                trend_label = f"{label} — **{duration}** {'upward' if direction == 'increasing' else 'downward'} trend"

                if direction == 'increasing':
                    buckets['ewma_increasing'].append(trend_label)
                elif direction == 'decreasing':
                    buckets['ewma_decreasing'].append(trend_label)

    # Build alert text
    lines = [
        "**CPM Anomaly Detection Alert**",
        f"**Date:** {date_str}",
        ""
    ]

    section_config = [
        ('matrix_profile', "Matrix Profile Anomalies",
         "*(Unusual subsequences detected — may forecast significant spikes or dips)*"),
        ('fourier', "Fourier Analysis Anomalies",
         "*(Significant frequency pattern changes detected)*"),
        ('custom', "Custom Method Anomalies",
         "*(Statistical outliers and unusual patterns detected)*"),
        ('ewma_increasing', "Increasing EWMA Trend Anomalies",
         "*(Significant upward trajectory)*"),
        ('ewma_decreasing', "Decreasing EWMA Trend Anomalies",
         "*(Significant downward trajectory)*"),
    ]

    any_found = False
    for key, title, desc in section_config:
        items = list(set(buckets[key]))  # Deduplicate
        if items:
            any_found = True
            lines.append(f"**{title}**")
            lines.append(desc)
            lines.extend(items)
            lines.append("")

    if not any_found:
        lines.append("No anomalies detected for the specified period.")

    return '\n'.join(lines)


def generate_json_alert(all_domain_anomalies: dict, alert_date,
                        incremental=False, previous_state=None) -> dict:
    """
    Generate structured JSON alert for downstream integration.
    This JSON is uploaded to GCS and consumed by the Smarty template
    pipeline that forwards to Slack.
    """
    date_str = f"{alert_date.month:02d}/{alert_date.day:02d}/{alert_date.year}"

    alert = {
        "alert_type": "CPM Anomaly Detection Alert",
        "date": date_str,
        "timestamp": alert_date.isoformat(),
        "anomalies": {
            "matrix_profile": [], "fourier_analysis": [],
            "custom_method": [], "ewma_increasing": [], "ewma_decreasing": []
        },
        "summary": {"total_domains_affected": 0, "total_anomalies": 0}
    }

    domains_affected = set()
    total = 0

    for domain_name, anomalies_df in all_domain_anomalies.items():
        if anomalies_df.empty:
            continue

        country_code, service = parse_domain_name(domain_name)

        if incremental and previous_state and 'last_date' in previous_state:
            relevant = anomalies_df[anomalies_df['time'] > previous_state['last_date']]
        else:
            relevant = anomalies_df[anomalies_df['date'] == alert_date.date()]

        if relevant.empty:
            continue

        domains_affected.add(domain_name)

        for _, anomaly in relevant.iterrows():
            total += 1
            entry = {
                "domain": domain_name,
                "country_code": country_code,
                "service": service,
                "time": anomaly['time'].isoformat() if pd.notnull(anomaly['time']) else None,
                "score": float(anomaly['anomaly_score']),
                "details": anomaly['details']
            }

            atype = anomaly['type']
            if atype == 'Matrix Profile':
                alert["anomalies"]["matrix_profile"].append(entry)
            elif atype == 'Fourier Analysis':
                alert["anomalies"]["fourier_analysis"].append(entry)
            elif atype == 'Custom':
                alert["anomalies"]["custom_method"].append(entry)
            elif atype == 'EWMA Trend':
                direction = anomaly.get('direction', '')
                entry["direction"] = direction
                if 'trajectory for' in anomaly.get('details', ''):
                    try:
                        days = anomaly['details'].split('trajectory for ')[1].split(' days')[0]
                        entry["trend_duration_days"] = int(days)
                    except (IndexError, ValueError):
                        pass
                if direction == 'increasing':
                    alert["anomalies"]["ewma_increasing"].append(entry)
                elif direction == 'decreasing':
                    alert["anomalies"]["ewma_decreasing"].append(entry)

    alert["summary"]["total_domains_affected"] = len(domains_affected)
    alert["summary"]["total_anomalies"] = total
    alert["summary"]["domains_affected"] = sorted(domains_affected)

    return alert


def generate_openai_alert(all_domain_anomalies: dict, alert_date,
                          incremental=False, previous_state=None) -> str:
    """
    Generate a GPT-4o enhanced alert with natural language summarization.
    Falls back to custom markdown format if API key is missing or call fails.
    
    ⚠️ MODIFIED: Uses OPENAI_API_KEY from environment instead of hardcoded key.
    """
    if not OPENAI_API_KEY:
        return generate_custom_alert(all_domain_anomalies, alert_date,
                                     incremental, previous_state)

    try:
        # Prepare anomaly data summary for the prompt
        anomaly_data = []
        for domain_name, anomalies_df in all_domain_anomalies.items():
            if anomalies_df.empty:
                continue
            if incremental and previous_state and 'last_date' in previous_state:
                relevant = anomalies_df[anomalies_df['time'] > previous_state['last_date']]
            else:
                relevant = anomalies_df[anomalies_df['date'] == alert_date.date()]

            for _, row in relevant.iterrows():
                anomaly_data.append({
                    "domain": domain_name,
                    "type": row['type'],
                    "anomaly_score": round(row['anomaly_score'], 3),
                    "details": row['details'],
                    "direction": row.get('direction', 'N/A')
                })

        if not anomaly_data:
            return generate_custom_alert(all_domain_anomalies, alert_date,
                                         incremental, previous_state)

        date_str = f"{alert_date.month:02d}/{alert_date.day:02d}/{alert_date.year}"

        prompt = f"""Generate an anomaly detection alert in this EXACT format:

**CPM Anomaly Detection Alert**
**Date:** {date_str}

Organize anomalies by type with these sections (only include sections that have anomalies):

**Matrix Profile Anomalies**
*(Unusual subsequences detected — may forecast significant spikes or dips)*
• [flag_emoji] **[country_code]-[service]**

**Fourier Analysis Anomalies**
*(Significant frequency pattern changes detected)*
• [flag_emoji] **[country_code]-[service]**

**Custom Method Anomalies**
*(Statistical outliers and unusual patterns detected)*
• [flag_emoji] **[country_code]-[service]**

**Increasing EWMA Trend Anomalies**
*(Significant upward trajectory)*
• [flag_emoji] **[country_code]-[service]** — **[X] days** upward trend

**Decreasing EWMA Trend Anomalies**
*(Significant downward trajectory)*
• [flag_emoji] **[country_code]-[service]** — **[X] days** downward trend

Rules:
1. Parse domain names to extract country codes (e.g., "US-api" → US)
2. Use appropriate flag emojis
3. For EWMA trends, extract duration from details field
4. Only include sections that have anomalies
5. Remove duplicate entries

Anomaly Data:
{json.dumps(anomaly_data, indent=2)}"""

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500
            }
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()

    except Exception as e:
        print(f"  OpenAI API error, using custom format: {e}")
        return generate_custom_alert(all_domain_anomalies, alert_date,
                                     incremental, previous_state)
```

---

## 10. Stage 7: Cloud Upload & Distribution

**Purpose:** Upload the JSON alert to Google Cloud Storage for downstream consumption.

```python
# ============================================================================
# STAGE 7: CLOUD UPLOAD — Push alert.json to GCS
# ============================================================================

def upload_alert_to_gcs(alert_json: dict,
                        bucket_name: str = GCS_BUCKET_NAME,
                        destination_blob: str = ALERT_GCS_PATH) -> str:
    """
    Upload alert JSON to GCS.
    Returns the public URL on success, None on failure.
    
    Note: Bucket uses uniform access control (IAM-based).
    Do NOT call blob.make_public() — that requires object-level ACL.
    """
    try:
        local_file = "alert.json"
        with open(local_file, 'w') as f:
            json.dump(alert_json, f, indent=2, default=str)

        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob)
        blob.upload_from_filename(local_file, content_type='application/json')

        public_url = f"https://storage.googleapis.com/{bucket_name}/{destination_blob}"
        print(f"  Alert uploaded: {public_url}")
        return public_url

    except Exception as e:
        print(f"  GCS upload failed: {e}")
        print("  Alert saved locally as alert.json")
        return None
```

---

## 11. Stage 8: Visualization & Dashboard

**Purpose:** Generate interactive Plotly HTML dashboards — per-domain detail pages and a cross-domain summary.

The visualization code is extensive (~500 lines) and is fully functional in the original. Key components:

1. **Per-domain plots (8 total per domain):**
   - Original signal with outliers highlighted
   - Fourier frequency band distribution + anomaly scores
   - Matrix Profile anomaly scores
   - Custom ensemble anomaly scores
   - EWMA trend analysis (signal + EWMA + trajectory markers)
   - Combined 5-panel overlay
   - Signal with all anomaly markers (color-coded by method)
   - EWMA trajectory analysis with streak annotations

2. **Cross-domain summary (index.html):**
   - Navigation bar linking to all domain pages
   - Cross-domain anomaly heatmap (Plotly imshow)
   - Most recent anomalies + EWMA trends per domain table
   - Consolidated alert display

3. **HTML template:** Uses Jinja2 with Plotly CDN, responsive CSS, anomaly table styling with `.new-anomaly` and `.recent-anomaly` CSS classes.

### ⚠️ NOTE FOR BUILD

The visualization functions (`visualize_results`, `generate_domain_report`, `generate_summary_report`, `generate_html`) are long but stable. They should be preserved as-is from the original code (lines 997–2345 in `cpm_ad.py`). The HTML template uses Jinja2 rendering with Plotly.js CDN.

---

## 12. Stage 9: Orchestration

**Purpose:** Unified main function that runs the full pipeline or individual stages.

### ⚠️ MODIFICATION REQUIRED: Unified CLI orchestrator

The original has multiple `if __name__ == "__main__"` blocks. The production version needs a single entry point.

```python
# ============================================================================
# STAGE 9: ORCHESTRATION — Unified pipeline runner
# ============================================================================

def run_full_pipeline(sensitivity='low', incremental=True, lookback_days=90,
                      gcs_bucket=GCS_BUCKET_NAME, skip_fetch=False):
    """
    Run the complete CPM anomaly detection pipeline:
    
    1. Fetch CPM data from ResGen API
    2. Clean and format
    3. Pivot to signal matrix
    4. Merge into historical signal.csv
    5. Run anomaly detection on all domains
    6. Generate alerts
    7. Upload to GCS
    8. Generate HTML dashboard
    """
    base_date = datetime.now()

    # --- Stages 1-4: Data Pipeline ---
    if not skip_fetch:
        print("=" * 60)
        print("STAGES 1-4: Data Pipeline")
        print("=" * 60)

        # Stage 1: Fetch
        raw_csv = fetch_cpm_data()

        # Stage 2: Clean
        cleaned_csv = clean_cpm_data(raw_csv, base_date)

        # Stage 3: Pivot
        signal_csv = pivot_to_signal_matrix(cleaned_csv, base_date)

        # Stage 4: Merge
        merge_daily_signal(signal_csv, base_date)

    # --- Stage 5-8: Analysis Pipeline ---
    print("\n" + "=" * 60)
    print("STAGES 5-8: Analysis Pipeline")
    print("=" * 60)

    # This calls the main() function from the anomaly detection engine
    main(
        file_path=LOCAL_SIGNAL_FILENAME,
        output_dir='anomaly_detection_results',
        sensitivity=sensitivity,
        incremental=incremental,
        lookback_days=lookback_days,
        gcs_bucket=gcs_bucket,
        gcs_path=ALERT_GCS_PATH
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='CPM Anomaly Detection Pipeline')
    parser.add_argument('--mode', choices=['full', 'fetch', 'merge', 'detect', 'download', 'upload', 'fix-dates'],
                        default='full', help='Pipeline mode')
    parser.add_argument('--sensitivity', choices=['low', 'medium', 'high'], default='low')
    parser.add_argument('--lookback', type=int, default=90)
    parser.add_argument('--date', type=str, help='Date override (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-upload', action='store_true')
    parser.add_argument('--skip-fetch', action='store_true')

    args = parser.parse_args()

    if args.mode == 'full':
        run_full_pipeline(
            sensitivity=args.sensitivity,
            incremental=True,
            lookback_days=args.lookback,
            skip_fetch=args.skip_fetch
        )
    elif args.mode == 'fetch':
        fetch_cpm_data()
    elif args.mode == 'merge':
        # Merge requires specifying which signal file
        run_daily_merge(date_str=args.date, dry_run=args.dry_run,
                        skip_upload=args.no_upload)
    elif args.mode == 'detect':
        main(file_path=LOCAL_SIGNAL_FILENAME,
             sensitivity=args.sensitivity,
             incremental=True, lookback_days=args.lookback)
    elif args.mode == 'download':
        download_signal_only()
    elif args.mode == 'upload':
        upload_existing_file()
    elif args.mode == 'fix-dates':
        fix_existing_signal_file()
```

---

## 13. Known Issues & Required Modifications

### 🔴 Critical

| Issue | Location | Fix Required |
|-------|----------|-------------|
| **Hardcoded OpenAI API key** | Original line 994 | Move to `OPENAI_API_KEY` env var. Original key is exposed and likely revoked. |
| **Multiple `if __name__` blocks** | Lines 272, 879, 2487 | Consolidate into single CLI entry point |
| **`!pip install` shell syntax** | Line 10 | Remove; add `requirements.txt` instead |
| **Duplicate imports** | Throughout | Consolidate at module top |

### 🟡 Important

| Issue | Location | Fix Required |
|-------|----------|-------------|
| **State persistence via local pickle** | `load_previous_state()` / `save_current_state()` | Add GCS-based state storage for cross-environment persistence |
| **Global mutable state** | `threshold_percentile`, `min_thresholds` as globals modified in `main()` | Pass as function parameters or use config dataclass |
| **Print-based logging** | Throughout | Replace with Python `logging` module |
| **No retry logic on API calls** | `http_fetch_json()`, GCS uploads | Add exponential backoff |

### 🟢 Enhancement

| Issue | Description |
|-------|------------|
| **No unit tests** | Add tests for date standardization, data flattening, anomaly scoring |
| **No typing for DataFrames** | Consider using pandera or dataframe schemas |
| **Visualization code duplication** | `visualize_results` and `generate_domain_report` duplicate anomaly threshold logic |
| **CLI help text** | Add examples in argparse epilog |

---

## 14. User Guide Reference

The system includes a comprehensive User Guide (Version 2.0) covering:

- **Detection Methods:** Detailed explanation of all 4 algorithms with interpretation guidance
- **Sensitivity Presets:** Low (99.5th %ile), Medium (99th), High (97.5th)
- **Input Format:** Wide CSV with Country_SourceType as first column, dates as remaining columns
- **Output Structure:** `anomaly_detection_results/` directory with index.html, per-domain HTML pages, state files, and alert.json
- **Domain Naming:** `XX-service` format (e.g., US-api, GB-xml) for flag emoji parsing
- **Best Practices:** Daily workflow, sensitivity guidelines, EWMA trajectory pattern interpretation
- **Troubleshooting:** Common issues with data format, GCS auth, sensitivity tuning

Key interpretation tables from the User Guide:

**EWMA Trajectory Action Thresholds:**
- 3-day increasing streak → Monitor
- 5+ day increasing streak → Investigate
- Increasing → Stable → Validate new baseline
- Oscillating → Deep dive for system instability

**Multi-Method Priority:**
- EWMA followed by others → High (early warning validated)
- All methods concurrent → Critical (major anomaly)
- Single method only → Medium (specific pattern type)

---

## 15. Build Instructions for Claude Code

### What to Build

A production-ready Python package called `cpm_anomaly_detection` with the following structure:

```
cpm_anomaly_detection/
├── __init__.py
├── config.py              # All configuration (env vars, constants, presets)
├── ingestion.py           # Stage 1: Fetch CPM data from ResGen API
├── cleaning.py            # Stage 2: Clean and format raw CSV
├── transform.py           # Stage 3: Pivot to signal matrix
├── merge.py               # Stage 4: Signal merge + GCS sync
├── detection/
│   ├── __init__.py
│   ├── preprocessing.py   # Data loading, outlier removal, state management
│   ├── fourier.py         # Method 1: Fourier Transform analysis
│   ├── matrix_profile.py  # Method 2: STUMPY Matrix Profile
│   ├── custom_ensemble.py # Method 3: Z-score + Seasonal + IsolationForest
│   ├── ewma.py            # Method 4: EWMA trend analysis
│   └── engine.py          # Orchestrates all 4 methods per domain
├── alerts/
│   ├── __init__.py
│   ├── custom.py          # Markdown alert with flag emojis
│   ├── json_alert.py      # Structured JSON alert
│   └── openai_alert.py    # Optional GPT-4o enhanced alert
├── cloud/
│   ├── __init__.py
│   └── gcs.py             # GCS upload/download utilities
├── visualization/
│   ├── __init__.py
│   ├── domain_plots.py    # Per-domain Plotly visualizations
│   ├── summary.py         # Cross-domain summary + heatmap
│   └── templates/
│       └── dashboard.html # Jinja2 HTML template
├── cli.py                 # Unified CLI entry point
├── pipeline.py            # Full pipeline orchestrator
├── requirements.txt
└── README.md
```

### Build Priorities

1. **First:** Get the data pipeline working end-to-end (Stages 1-4)
2. **Second:** Port the anomaly detection engine with all 4 methods
3. **Third:** Alert generation (custom markdown + JSON)
4. **Fourth:** Visualization (port the Plotly code)
5. **Fifth:** CLI interface and orchestration
6. **Last:** OpenAI integration (optional enhancement)

### Key Constraints

- Must run in Google Colab, Vertex AI Workbench, and standalone Python
- GCS authentication via `gcloud auth application-default login` or service account
- All secrets from environment variables (never hardcoded)
- Preserve the exact alert format (flag emojis, markdown structure) — downstream Slack integration depends on it
- The `signal.csv` format (M/D/YYYY date columns) is the contract with GCS consumers
- Sensitivity presets must produce identical thresholds to the original

### Code You Can Port Directly

The following functions from the original are stable and can be used as-is with minimal cleanup:
- All detection algorithms (fourier_analysis, matrix_profile_analysis, custom_anomaly_detection, ewma_analysis)
- All visualization functions (visualize_results, generate_domain_report, generate_summary_report)
- The HTML template and generate_html function
- Date column standardization logic
- Alert formatting (custom_alert, json_alert)

### Code That Needs Rewriting

- Configuration management (externalize everything)
- State persistence (pickle → GCS-based)
- Main orchestration (merge the three `__main__` blocks)
- Logging (print → logging module)
- Error handling (add proper exception hierarchy)
