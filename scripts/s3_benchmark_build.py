"""
Subagent 3: BENCHMARK_BUILD
=============================
Compute demographic and earnings benchmarks for comparison groups.
Used by both Paper 1 (aging) and Paper 2 (disparity).

Usage:
    python scripts/s3_benchmark_build.py --ipums data/raw/usa_00001.csv --output data/benchmarks.csv

This reads the FULL IPUMS extract (not the filtered surveyor file) to compute
workforce-wide benchmarks. It filters to employed civilians age 18+.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Benchmark group definitions by OCC code ranges
BENCHMARK_GROUPS = {
    "Surveyors": [1530],
    "Survey technicians": [1560],
    "Cartographers": [1520],
    "All STEM": list(range(1000, 1981)) + list(range(2100, 2161)),
    "Architecture & engineering": list(range(1300, 1561)),
    "Construction trades": list(range(6200, 6766)),
}

# Race/ethnicity recode (same logic as s2_recode.py)
def recode_race_eth(df):
    conditions = [
        df["HISPAN"].between(1, 4),
        (df["HISPAN"] == 0) & (df["RACE"] == 1),
        (df["HISPAN"] == 0) & (df["RACE"] == 2),
        (df["HISPAN"] == 0) & (df["RACE"].isin([4, 5, 6])),
        (df["HISPAN"] == 0) & (df["RACE"] == 3),
        (df["HISPAN"] == 0),
    ]
    choices = ["Hispanic", "NH White", "NH Black", "NH Asian", "NH AIAN",
               "NH Other/Multiracial"]
    return pd.Series(np.select(conditions, choices, default="Unknown"), index=df.index)


def recode_sex(df):
    return df["SEX"].map({1: "Male", 2: "Female"})


def recode_educ(df):
    conditions = [
        df["EDUCD"] <= 61,
        df["EDUCD"].between(62, 81),
        df["EDUCD"] == 101,
        df["EDUCD"] >= 114,
    ]
    choices = ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]
    return pd.Series(np.select(conditions, choices, default="Unknown"), index=df.index)


def recode_agegroup(df):
    bins = [17, 24, 34, 44, 54, 64, 120]
    labels = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    return pd.cut(df["AGE"], bins=bins, labels=labels, right=True)


def weighted_median(values, weights):
    """Compute weighted median."""
    mask = values.notna() & weights.notna() & (weights > 0)
    v = values[mask].values
    w = weights[mask].values
    if len(v) == 0:
        return np.nan
    sorted_idx = np.argsort(v)
    v_sorted = v[sorted_idx]
    w_sorted = w[sorted_idx]
    cumw = np.cumsum(w_sorted)
    cutoff = cumw[-1] / 2.0
    idx = np.searchsorted(cumw, cutoff)
    return v_sorted[min(idx, len(v_sorted) - 1)]


def compute_group_stats(df, group_name, perwt_col="PERWT"):
    """Compute demographic proportions and age stats for a group."""
    wt = df[perwt_col]
    total_wt = wt.sum()

    stats = {"group": group_name, "weighted_n": total_wt, "unweighted_n": len(df)}

    # Weighted median age
    stats["median_age"] = weighted_median(df["AGE"], wt)

    # Age shares
    for age_label in ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]:
        mask = df["agegroup"] == age_label
        stats[f"pct_age_{age_label}"] = (wt[mask].sum() / total_wt * 100) if total_wt > 0 else 0

    # Share 55+
    stats["pct_55plus"] = (wt[df["AGE"] >= 55].sum() / total_wt * 100) if total_wt > 0 else 0

    # Share 18-34
    stats["pct_18_34"] = (wt[df["AGE"] <= 34].sum() / total_wt * 100) if total_wt > 0 else 0

    # Sex shares
    for sex_label in ["Male", "Female"]:
        mask = df["sex_r"] == sex_label
        stats[f"pct_{sex_label.lower()}"] = (wt[mask].sum() / total_wt * 100) if total_wt > 0 else 0

    # Race/ethnicity shares
    for re in ["NH White", "NH Black", "Hispanic", "NH Asian", "NH AIAN",
               "NH Other/Multiracial"]:
        mask = df["race_eth"] == re
        stats[f"pct_{re.replace(' ', '_').replace('/', '_')}"] = (
            wt[mask].sum() / total_wt * 100) if total_wt > 0 else 0

    # Education shares
    for ed in ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]:
        mask = df["educ_r"] == ed
        stats[f"pct_educ_{ed.replace(' ', '_').replace('/', '_')}"] = (
            wt[mask].sum() / total_wt * 100) if total_wt > 0 else 0

    # Veteran share (among those with valid VETSTAT)
    valid_vet = df[df["VETSTAT"].isin([1, 2])]
    if len(valid_vet) > 0:
        vet_wt = valid_vet[perwt_col]
        stats["pct_veteran"] = (
            vet_wt[valid_vet["VETSTAT"] == 2].sum() / vet_wt.sum() * 100
        )
    else:
        stats["pct_veteran"] = np.nan

    return stats


def main():
    parser = argparse.ArgumentParser(description="Subagent 3: BENCHMARK_BUILD")
    parser.add_argument("--ipums", required=True,
                        help="Path to FULL IPUMS extract (not filtered)")
    parser.add_argument("--output", default="data/benchmarks.csv",
                        help="Output path for benchmarks")
    args = parser.parse_args()

    input_path = Path(args.ipums)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    # We need to process the full IPUMS file but only keep columns we need
    needed_cols = ["YEAR", "PERWT", "OCC", "SEX", "AGE", "RACE", "HISPAN",
                   "EDUCD", "EMPSTAT", "CLASSWKR", "VETSTAT"]

    print(f"Loading IPUMS extract: {input_path}")
    print("  (This reads the full file to build workforce benchmarks.)")
    print("  Processing in chunks to manage memory...")

    all_groups = {}

    # Initialize storage for each benchmark group + general workforce
    group_frames = {name: [] for name in BENCHMARK_GROUPS}
    group_frames["U.S. workforce"] = []

    chunk_iter = pd.read_csv(input_path, chunksize=500_000, low_memory=False,
                             usecols=lambda c: c.upper() in [x.upper() for x in needed_cols])

    for i, chunk in enumerate(chunk_iter):
        chunk.columns = chunk.columns.str.upper()

        # Filter to employed civilians age 18+
        chunk = chunk[(chunk["EMPSTAT"] == 1) & (chunk["AGE"] >= 18)].copy()

        if len(chunk) == 0:
            continue

        # Apply recodes
        chunk["sex_r"] = recode_sex(chunk)
        chunk["race_eth"] = recode_race_eth(chunk)
        chunk["educ_r"] = recode_educ(chunk)
        chunk["agegroup"] = recode_agegroup(chunk)

        # General workforce
        group_frames["U.S. workforce"].append(chunk)

        # Specific occupation groups
        for group_name, occ_codes in BENCHMARK_GROUPS.items():
            filtered = chunk[chunk["OCC"].isin(occ_codes)]
            if len(filtered) > 0:
                group_frames[group_name].append(filtered)

        if (i + 1) % 10 == 0:
            print(f"  Processed {(i+1) * 500_000:,} rows...")

    # Compute stats for each group
    print("\nComputing benchmark statistics...")
    results = []

    for group_name, frames in group_frames.items():
        if not frames:
            print(f"  {group_name}: No data found.")
            continue

        group_df = pd.concat(frames, ignore_index=True)
        stats = compute_group_stats(group_df, group_name)
        results.append(stats)
        print(f"  {group_name}: N={stats['weighted_n']:,.0f}, "
              f"median age={stats['median_age']:.1f}, "
              f"55+={stats['pct_55plus']:.1f}%, "
              f"female={stats['pct_female']:.1f}%, "
              f"NH White={stats['pct_NH_White']:.1f}%")

    # Build output
    benchmarks = pd.DataFrame(results)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving benchmarks to: {output_path}")
    benchmarks.to_csv(output_path, index=False)
    print(f"Done. {len(benchmarks)} benchmark groups saved.")


if __name__ == "__main__":
    main()
