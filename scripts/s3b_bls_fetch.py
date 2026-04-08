"""
Subagent 3B: BLS_FETCH
========================
Retrieve supplemental data from BLS APIs and web pages.
Pulls OEWS data for SOC 17-1022 (Surveyors) and 17-3031 (Technicians).

Usage:
    python scripts/s3b_bls_fetch.py --output-dir data/supplemental/

Note: BLS public API allows 25 series per query, 500 requests/day without a key.
      If you have a BLS API key, pass it with --api-key.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests
import pandas as pd

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# OEWS series IDs for Surveyors (SOC 17-1022)
# Format: OEU + seasonal_code + area_code + industry_code + occupation_code + data_type
# National data: OEUN000000000000017102201 (employment), 04 (mean wage), 13 (median wage)
SERIES = {
    # Surveyors employment and wages (national)
    "surveyors_employment": "OEUM000000000000017102201",
    "surveyors_mean_wage": "OEUM000000000000017102204",
    "surveyors_median_wage": "OEUM000000000000017102213",
    "surveyors_10pct_wage": "OEUM000000000000017102207",
    "surveyors_25pct_wage": "OEUM000000000000017102208",
    "surveyors_75pct_wage": "OEUM000000000000017102209",
    "surveyors_90pct_wage": "OEUM000000000000017102210",
    # Survey & mapping technicians (SOC 17-3031)
    "technicians_employment": "OEUM000000000000017303101",
    "technicians_mean_wage": "OEUM000000000000017303104",
    "technicians_median_wage": "OEUM000000000000017303113",
}


def fetch_bls_series(series_ids: dict, start_year: int = 2014,
                     end_year: int = 2024, api_key: str = None) -> pd.DataFrame:
    """Fetch time series data from BLS API."""

    headers = {"Content-type": "application/json"}
    payload = {
        "seriesid": list(series_ids.values()),
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    if api_key:
        payload["registrationkey"] = api_key

    print(f"Fetching {len(series_ids)} series from BLS API ({start_year}-{end_year})...")

    try:
        response = requests.post(BLS_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR: BLS API request failed: {e}")
        print("  The BLS API may be temporarily unavailable.")
        print("  You can re-run this script later, or manually download data from:")
        print("  https://www.bls.gov/oes/current/oes171022.htm")
        return pd.DataFrame()

    data = response.json()

    if data.get("status") != "REQUEST_SUCCEEDED":
        print(f"ERROR: BLS API returned status: {data.get('status')}")
        if "message" in data:
            for msg in data["message"]:
                print(f"  {msg}")
        return pd.DataFrame()

    # Parse results
    id_to_name = {v: k for k, v in series_ids.items()}
    rows = []

    for series in data.get("Results", {}).get("series", []):
        series_id = series["seriesID"]
        series_name = id_to_name.get(series_id, series_id)

        for item in series.get("data", []):
            rows.append({
                "series_name": series_name,
                "series_id": series_id,
                "year": int(item["year"]),
                "period": item["period"],
                "value": item["value"],
            })

    df = pd.DataFrame(rows)
    print(f"  Retrieved {len(df)} data points.")
    return df


def reshape_bls_data(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape from long to wide format for easier use."""
    if df.empty:
        return df

    # Filter to annual data only (period M13 = annual average for OEWS)
    annual = df[df["period"] == "A01"].copy()
    if annual.empty:
        # Try M13 (annual mean)
        annual = df[df["period"] == "M13"].copy()
    if annual.empty:
        # Use whatever period is available
        annual = df.copy()
        print("  NOTE: Could not isolate annual data. Using all periods.")

    # Pivot
    wide = annual.pivot_table(
        index="year", columns="series_name", values="value", aggfunc="first"
    ).reset_index()

    return wide


def create_projections_csv(output_dir: Path):
    """Create BLS projections file from known published data."""
    # From BLS OOH 2024-2034 projections (published 2025)
    projections = pd.DataFrame([
        {"soc": "17-1022", "occupation": "Surveyors",
         "base_year": 2024, "projected_year": 2034,
         "growth_rate_pct": 4, "annual_openings": 3900,
         "median_wage_2024": 72740,
         "source": "BLS Occupational Outlook Handbook 2024-2034"},
        {"soc": "17-3031", "occupation": "Surveying and mapping technicians",
         "base_year": 2024, "projected_year": 2034,
         "growth_rate_pct": 5, "annual_openings": 7600,
         "median_wage_2024": 48380,
         "source": "BLS Occupational Outlook Handbook 2024-2034"},
    ])

    output_path = output_dir / "bls_projections.csv"
    projections.to_csv(output_path, index=False)
    print(f"  Saved projections to: {output_path}")
    return projections


def main():
    parser = argparse.ArgumentParser(description="Subagent 3B: BLS_FETCH")
    parser.add_argument("--output-dir", default="data/supplemental/",
                        help="Output directory for BLS data")
    parser.add_argument("--api-key", default=None,
                        help="BLS API registration key (optional)")
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch OEWS data
    df = fetch_bls_series(SERIES, args.start_year, args.end_year, args.api_key)

    if not df.empty:
        # Save raw long format
        raw_path = output_dir / "bls_oews_raw.csv"
        df.to_csv(raw_path, index=False)
        print(f"  Saved raw data to: {raw_path}")

        # Save reshaped wide format
        wide = reshape_bls_data(df)
        wide_path = output_dir / "bls_oews_surveyors.csv"
        wide.to_csv(wide_path, index=False)
        print(f"  Saved reshaped data to: {wide_path}")
    else:
        print("\n  NOTE: BLS API fetch returned no data.")
        print("  Creating placeholder file with known BLS published values.")
        # Fallback: known values from BLS website
        fallback = pd.DataFrame([
            {"year": 2024, "surveyors_employment": "~45,300",
             "surveyors_median_wage": 72740,
             "technicians_employment": "~56,900",
             "technicians_median_wage": 48380,
             "source": "BLS OES May 2024 (manual entry)"},
        ])
        fallback_path = output_dir / "bls_oews_surveyors.csv"
        fallback.to_csv(fallback_path, index=False)
        print(f"  Saved fallback data to: {fallback_path}")

    # Create projections file
    print("\nCreating BLS projections file...")
    create_projections_csv(output_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
