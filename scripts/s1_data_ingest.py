"""
Subagent 1: DATA_INGEST
========================
Load IPUMS ACS extract, filter to surveying occupations, validate completeness.

Usage:
    python scripts/s1_data_ingest.py --input data/raw/usa_00001.csv --output data/surveying_filtered.csv

If using .dta (Stata) format:
    python scripts/s1_data_ingest.py --input data/raw/usa_00001.dta --output data/surveying_filtered.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Target occupation codes (Census OCC)
TARGET_OCC = {
    1520: "Cartographers and photogrammetrists",
    1530: "Surveyors",
    1560: "Surveying and mapping technicians",
}

# Required variables for analysis
# Note: EDUC or EDUCD — IPUMS includes EDUCD automatically with EDUC, but
# the script accepts either. s2_recode.py handles both.
REQUIRED_VARS = [
    "YEAR", "PERWT", "OCC", "SEX", "AGE", "RACE", "HISPAN",
    "EMPSTAT", "CLASSWKR", "WKSWORK2", "UHRSWORK",
    "INCWAGE", "INCEARN", "VETSTAT", "STATEFIP", "METRO", "IND",
]
# At least one of these must be present
EDUC_VARS = ["EDUCD", "EDUC"]

# Replicate weight columns
REPWT_COLS = [f"REPWTP{i}" for i in range(1, 81)]

# Expected weighted sample size ranges
EXPECTED_RANGES = {
    1530: (80_000, 120_000),
    1560: (60_000, 100_000),
    1520: (15_000, 30_000),
}


def load_data(filepath: Path) -> pd.DataFrame:
    """Load IPUMS extract in CSV or Stata format."""
    suffix = filepath.suffix.lower()

    if suffix == ".csv":
        print(f"Loading CSV: {filepath}")
        # Read in chunks to manage memory, filtering as we go
        chunks = []
        chunk_iter = pd.read_csv(
            filepath,
            chunksize=500_000,
            low_memory=False,
        )
        for i, chunk in enumerate(chunk_iter):
            # Normalize column names to uppercase
            chunk.columns = chunk.columns.str.upper()
            # Filter to target occupations immediately to save memory
            filtered = chunk[chunk["OCC"].isin(TARGET_OCC.keys())]
            if len(filtered) > 0:
                chunks.append(filtered)
            if (i + 1) % 10 == 0:
                print(f"  Processed {(i+1) * 500_000:,} rows...")

        if not chunks:
            print("ERROR: No rows found matching target occupation codes.")
            print(f"  Looked for OCC in {list(TARGET_OCC.keys())}")
            sys.exit(1)

        df = pd.concat(chunks, ignore_index=True)

    elif suffix == ".dta":
        print(f"Loading Stata file: {filepath}")
        import pyreadstat
        df, meta = pyreadstat.read_dta(filepath)
        df.columns = df.columns.str.upper()
        df = df[df["OCC"].isin(TARGET_OCC.keys())].copy()

    elif suffix in (".dat", ".gz"):
        print(f"Loading fixed-width/IPUMS format: {filepath}")
        print("For .dat files, use ipumspy with the DDI XML codebook.")
        print("Convert to CSV first, or use the .dta download option.")
        sys.exit(1)

    else:
        print(f"ERROR: Unsupported file format: {suffix}")
        sys.exit(1)

    print(f"Loaded {len(df):,} rows matching target occupations.")
    return df


def validate_variables(df: pd.DataFrame) -> bool:
    """Check that all required variables are present."""
    missing = [v for v in REQUIRED_VARS if v not in df.columns]
    if missing:
        print(f"WARNING: Missing required variables: {missing}")
        print("  These variables are needed for the analysis pipeline.")
        print("  Please check your IPUMS extract includes them.")
        return False

    # Check education variable (EDUCD preferred, EDUC acceptable)
    has_educ = any(v in df.columns for v in EDUC_VARS)
    if not has_educ:
        print("WARNING: Neither EDUCD nor EDUC found.")
        print("  Add EDUC to your IPUMS extract (EDUCD comes automatically).")
        return False
    else:
        educ_found = [v for v in EDUC_VARS if v in df.columns]
        print(f"  Education variable(s) present: {educ_found}")

    # Check replicate weights
    repwt_present = [c for c in REPWT_COLS if c in df.columns]
    repwt_missing = [c for c in REPWT_COLS if c not in df.columns]

    if len(repwt_present) == 0:
        print("CRITICAL: No replicate weights (REPWTP1-REPWTP80) found.")
        print("  BRR variance estimation requires replicate weights.")
        print("  Please re-submit your IPUMS extract with REPWTP selected.")
        print("  HALTING.")
        sys.exit(1)
    elif len(repwt_missing) > 0:
        print(f"WARNING: {len(repwt_missing)} replicate weights missing:")
        print(f"  Missing: {repwt_missing[:5]}... ({len(repwt_missing)} total)")
        print("  Expected 80 replicate weights (REPWTP1-REPWTP80).")
        return False
    else:
        print(f"  All 80 replicate weights present.")

    print(f"  All {len(REQUIRED_VARS)} required variables present.")
    return True


def report_counts(df: pd.DataFrame):
    """Report unweighted and weighted counts by occupation."""
    print("\n" + "=" * 60)
    print("SAMPLE COUNTS BY OCCUPATION")
    print("=" * 60)

    for occ_code, occ_label in TARGET_OCC.items():
        subset = df[df["OCC"] == occ_code]
        n_unweighted = len(subset)
        n_weighted = subset["PERWT"].sum() if "PERWT" in df.columns else 0

        print(f"\n  OCC {occ_code} ({occ_label}):")
        print(f"    Unweighted n: {n_unweighted:,}")
        print(f"    Weighted N:   {n_weighted:,.0f}")

        # Check against expected ranges
        if occ_code in EXPECTED_RANGES:
            lo, hi = EXPECTED_RANGES[occ_code]
            if n_weighted < 10_000:
                print(f"    *** ALERT: Weighted N below 10,000. Subgroup analysis will be limited.")
            elif n_weighted < lo:
                print(f"    NOTE: Below expected range ({lo:,}-{hi:,}).")
            elif n_weighted > hi:
                print(f"    NOTE: Above expected range ({lo:,}-{hi:,}).")
            else:
                print(f"    Within expected range ({lo:,}-{hi:,}).")


def flag_data_quality(df: pd.DataFrame):
    """Flag potential data quality issues."""
    print("\n" + "=" * 60)
    print("DATA QUALITY FLAGS")
    print("=" * 60)

    # INCEARN top-coding
    if "INCEARN" in df.columns:
        employed = df[df["EMPSTAT"] == 1] if "EMPSTAT" in df.columns else df
        nonzero_earn = employed[employed["INCEARN"] > 0]
        if len(nonzero_earn) > 0:
            max_earn = nonzero_earn["INCEARN"].max()
            at_max = (nonzero_earn["INCEARN"] == max_earn).sum()
            pct_at_max = at_max / len(nonzero_earn) * 100
            print(f"\n  INCEARN top-coding:")
            print(f"    Maximum value: ${max_earn:,.0f}")
            print(f"    Cases at maximum: {at_max} ({pct_at_max:.1f}%)")
            if pct_at_max > 15:
                print(f"    *** FLAG: >{pct_at_max:.0f}% at ceiling. Top-coding may affect wage analysis.")
            else:
                print(f"    OK: Below 15% threshold.")

    # Zero earnings among employed
    if "INCEARN" in df.columns and "EMPSTAT" in df.columns:
        employed = df[df["EMPSTAT"] == 1]
        zero_earn = (employed["INCEARN"] == 0).sum()
        pct_zero = zero_earn / len(employed) * 100 if len(employed) > 0 else 0
        print(f"\n  Zero INCEARN among employed:")
        print(f"    Cases: {zero_earn} ({pct_zero:.1f}%)")
        if pct_zero > 20:
            print(f"    *** FLAG: >{pct_zero:.0f}% zero earnings. Check for non-response.")
        else:
            print(f"    OK: Below 20% threshold.")

    # IPUMS missing codes
    ipums_missing = [999998, 999999, 9999998, 9999999]
    for var in ["INCEARN", "INCWAGE", "EDUCD"]:
        if var in df.columns:
            n_missing = df[var].isin(ipums_missing).sum()
            if n_missing > 0:
                print(f"\n  *** FLAG: {var} has {n_missing} IPUMS missing codes (999998/999999).")
                print(f"    These must be recoded to NaN before analysis.")


def main():
    parser = argparse.ArgumentParser(description="Subagent 1: DATA_INGEST")
    parser.add_argument("--input", required=True, help="Path to IPUMS extract file")
    parser.add_argument("--output", default="data/surveying_filtered.csv",
                        help="Output path for filtered data")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load and filter
    df = load_data(input_path)

    # Validate
    validate_variables(df)

    # Report counts
    report_counts(df)

    # Quality flags
    flag_data_quality(df)

    # Save
    print(f"\nSaving filtered data to: {output_path}")
    df.to_csv(output_path, index=False)
    print(f"Done. {len(df):,} rows saved.")
    print(f"File size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
