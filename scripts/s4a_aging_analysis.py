"""
Subagent 4A: AGING_ANALYSIS
=============================
Produce all age-distribution, retirement-cliff, and geographic-aging tables
for Paper 1 (Workforce Aging and Contraction).

Reads person-level ACS microdata (OCC 1530 Surveyors, 1560 Technicians,
1520 Cartographers) already recoded by s2_recode.py, along with
workforce-wide benchmarks built by s3_benchmark_build.py.

Variance estimation uses Fay's BRR with k = 0.5 and the 80 ACS replicate
weights (REPWTP1-REPWTP80).

Usage:
    python scripts/s4a_aging_analysis.py
    python scripts/s4a_aging_analysis.py --input data/surveying_recoded.csv \
           --benchmarks data/benchmarks.csv --outdir analysis/p1
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# STATEFIP -> state name mapping (50 states + DC)
# ---------------------------------------------------------------------------
STATEFIP_MAP = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas",
    6: "California", 8: "Colorado", 9: "Connecticut", 10: "Delaware",
    11: "District of Columbia", 12: "Florida", 13: "Georgia", 15: "Hawaii",
    16: "Idaho", 17: "Illinois", 18: "Indiana", 19: "Iowa",
    20: "Kansas", 21: "Kentucky", 22: "Louisiana", 23: "Maine",
    24: "Maryland", 25: "Massachusetts", 26: "Michigan", 27: "Minnesota",
    28: "Mississippi", 29: "Missouri", 30: "Montana", 31: "Nebraska",
    32: "Nevada", 33: "New Hampshire", 34: "New Jersey", 35: "New Mexico",
    36: "New York", 37: "North Carolina", 38: "North Dakota", 39: "Ohio",
    40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania", 44: "Rhode Island",
    45: "South Carolina", 46: "South Dakota", 47: "Tennessee", 48: "Texas",
    49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington",
    54: "West Virginia", 55: "Wisconsin", 56: "Wyoming",
}

# Fay BRR perturbation factor
FAY_K = 0.5

# Number of ACS replicate weights
N_REPS = 80

# Replicate weight column names
REPWT_COLS = [f"REPWTP{i}" for i in range(1, N_REPS + 1)]

# Minimum unweighted n for state-level reporting
MIN_STATE_N = 30

# Assumed retirement age for projection
RETIREMENT_AGE = 65


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def weighted_median(values, weights):
    """Compute the weighted median of *values* using *weights*.

    Returns np.nan when no valid observations remain after dropping NaN/zero-
    weight records.
    """
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
    return float(v_sorted[min(idx, len(v_sorted) - 1)])


def weighted_mean(values, weights):
    """Compute the weighted mean; returns np.nan when empty."""
    mask = values.notna() & weights.notna() & (weights > 0)
    v = values[mask].values
    w = weights[mask].values
    if len(v) == 0 or w.sum() == 0:
        return np.nan
    return float(np.average(v, weights=w))


def weighted_share(mask_series, weights):
    """Weighted share (0-100) of *mask_series* (boolean) using *weights*."""
    total = weights.sum()
    if total == 0:
        return np.nan
    return float(weights[mask_series].sum() / total * 100)


def brr_se(replicate_estimates, full_estimate, k=FAY_K):
    """Fay BRR standard error.

    SE = sqrt( (1 / (R * (1-k)^2)) * sum( (theta_r - theta)^2 ) )

    where R is the number of replicates and k is the Fay factor.
    """
    reps = np.asarray(replicate_estimates, dtype=float)
    diffs_sq = (reps - full_estimate) ** 2
    variance = diffs_sq.sum() / (len(reps) * (1 - k) ** 2)
    return float(np.sqrt(variance))


def ci_95(estimate, se):
    """Return (lower, upper) 95 % confidence interval."""
    return (estimate - 1.96 * se, estimate + 1.96 * se)


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------
def compute_age_stats(df, group_label, wt_col="PERWT"):
    """Return a dict of age-distribution statistics for one group."""
    wt = df[wt_col]
    total_wt = wt.sum()
    stats = {
        "group": group_label,
        "weighted_n": total_wt,
        "unweighted_n": len(df),
    }

    # Weighted median age ---------------------------------------------------
    full_median = weighted_median(df["AGE"], wt)
    stats["median_age"] = full_median

    # BRR SE for median age -------------------------------------------------
    has_repwts = all(c in df.columns for c in REPWT_COLS)
    if has_repwts and len(df) > 0:
        rep_medians = [
            weighted_median(df["AGE"], df[rc]) for rc in REPWT_COLS
        ]
        se = brr_se(rep_medians, full_median)
        lo, hi = ci_95(full_median, se)
        stats["median_age_SE"] = se
        stats["median_age_CI_lo"] = lo
        stats["median_age_CI_hi"] = hi
    else:
        stats["median_age_SE"] = np.nan
        stats["median_age_CI_lo"] = np.nan
        stats["median_age_CI_hi"] = np.nan

    # Age shares ------------------------------------------------------------
    stats["pct_18_34"] = weighted_share(df["AGE"] <= 34, wt) if total_wt else np.nan
    stats["pct_55plus"] = weighted_share(df["AGE"] >= 55, wt) if total_wt else np.nan
    stats["pct_65plus"] = weighted_share(df["AGE"] >= 65, wt) if total_wt else np.nan

    # Years-until-retirement for workers 45+ --------------------------------
    older = df[df["AGE"] >= 45].copy()
    if len(older) > 0:
        ytr = RETIREMENT_AGE - older["AGE"]
        stats["mean_years_to_retire_45plus"] = weighted_mean(ytr, older[wt_col])
        stats["median_years_to_retire_45plus"] = weighted_median(ytr, older[wt_col])
    else:
        stats["mean_years_to_retire_45plus"] = np.nan
        stats["median_years_to_retire_45plus"] = np.nan

    return stats


def build_age_distribution_table(df, benchmarks_df):
    """Requirement 1 + 4: Age distribution / benchmark comparison table.

    Computes stats for surveyors, technicians, and cartographers from the
    micro data.  Appends rows for benchmark groups read from benchmarks.csv
    (which lack replicate weights, so SE is not available for those).
    """
    rows = []

    # Micro-data groups with BRR SE
    for occ_code, label in [(1530, "Surveyors"), (1560, "Survey technicians"),
                            (1520, "Cartographers")]:
        sub = df[df["OCC"] == occ_code]
        if len(sub) == 0:
            print(f"  WARNING: No records for OCC={occ_code} ({label})")
            continue
        stats = compute_age_stats(sub, label)
        rows.append(stats)
        print(f"  {label}: median age {stats['median_age']:.1f} "
              f"(SE={stats['median_age_SE']:.2f}), "
              f"55+={stats['pct_55plus']:.1f}%, "
              f"18-34={stats['pct_18_34']:.1f}%")

    # Benchmark groups (already aggregated; no replicate weights)
    if benchmarks_df is not None and len(benchmarks_df) > 0:
        # Identify groups that are NOT already computed above
        micro_labels = {"Surveyors", "Survey technicians", "Cartographers"}
        for _, row in benchmarks_df.iterrows():
            gname = row["group"]
            if gname in micro_labels:
                continue  # skip, we computed these with SE above
            brow = {
                "group": gname,
                "weighted_n": row.get("weighted_n", np.nan),
                "unweighted_n": row.get("unweighted_n", np.nan),
                "median_age": row.get("median_age", np.nan),
                "median_age_SE": np.nan,
                "median_age_CI_lo": np.nan,
                "median_age_CI_hi": np.nan,
                "pct_18_34": row.get("pct_18_34", np.nan),
                "pct_55plus": row.get("pct_55plus", np.nan),
                "pct_65plus": row.get("pct_65plus", np.nan),
                "mean_years_to_retire_45plus": np.nan,
                "median_years_to_retire_45plus": np.nan,
            }
            rows.append(brow)

    return pd.DataFrame(rows)


def build_retirement_cliff(df):
    """Requirement 2: Retirement cliff projection for OCC=1530."""
    surveyors = df[df["OCC"] == 1530].copy()
    if len(surveyors) == 0:
        print("  WARNING: No OCC=1530 records for retirement cliff.")
        return pd.DataFrame()

    wt = surveyors["PERWT"]
    total_wt = wt.sum()

    # 55+ block
    mask_55plus = surveyors["AGE"] >= 55
    n_55plus_wt = wt[mask_55plus].sum()
    pct_55plus = n_55plus_wt / total_wt * 100 if total_wt else np.nan

    # 18-34 block (replacement pipeline)
    mask_18_34 = surveyors["AGE"] <= 34
    n_18_34_wt = wt[mask_18_34].sum()
    pct_18_34 = n_18_34_wt / total_wt * 100 if total_wt else np.nan

    # Cliff gap
    cliff_gap = pct_55plus - pct_18_34

    # BRR SE for pct_55plus
    has_repwts = all(c in surveyors.columns for c in REPWT_COLS)
    if has_repwts:
        rep_pct_55 = []
        rep_pct_18_34 = []
        for rc in REPWT_COLS:
            rw = surveyors[rc]
            rw_total = rw.sum()
            if rw_total > 0:
                rep_pct_55.append(rw[mask_55plus].sum() / rw_total * 100)
                rep_pct_18_34.append(rw[mask_18_34].sum() / rw_total * 100)
            else:
                rep_pct_55.append(np.nan)
                rep_pct_18_34.append(np.nan)
        se_55plus = brr_se(rep_pct_55, pct_55plus)
        se_18_34 = brr_se(rep_pct_18_34, pct_18_34)
        # SE for the gap (difference of correlated shares)
        rep_gaps = [r55 - r34 for r55, r34 in zip(rep_pct_55, rep_pct_18_34)]
        se_gap = brr_se(rep_gaps, cliff_gap)
    else:
        se_55plus = np.nan
        se_18_34 = np.nan
        se_gap = np.nan

    # Projected retirement within 5 and 10 years
    mask_60plus = surveyors["AGE"] >= 60
    pct_60plus = wt[mask_60plus].sum() / total_wt * 100 if total_wt else np.nan
    mask_55_64 = (surveyors["AGE"] >= 55) & (surveyors["AGE"] <= 64)
    n_55_64_wt = wt[mask_55_64].sum()

    # Years-to-retirement stats for 45+
    older = surveyors[surveyors["AGE"] >= 45].copy()
    ytr = RETIREMENT_AGE - older["AGE"]
    mean_ytr = weighted_mean(ytr, older["PERWT"])
    median_ytr = weighted_median(ytr, older["PERWT"])

    rows = [
        {
            "metric": "Total surveyor workforce (weighted N)",
            "value": total_wt,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Weighted N aged 55+",
            "value": n_55plus_wt,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Pct 55+ of workforce",
            "value": pct_55plus,
            "SE": se_55plus,
            "CI_95_lo": pct_55plus - 1.96 * se_55plus if not np.isnan(se_55plus) else np.nan,
            "CI_95_hi": pct_55plus + 1.96 * se_55plus if not np.isnan(se_55plus) else np.nan,
        },
        {
            "metric": "Weighted N aged 18-34",
            "value": n_18_34_wt,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Pct 18-34 of workforce (replacement pipeline)",
            "value": pct_18_34,
            "SE": se_18_34,
            "CI_95_lo": pct_18_34 - 1.96 * se_18_34 if not np.isnan(se_18_34) else np.nan,
            "CI_95_hi": pct_18_34 + 1.96 * se_18_34 if not np.isnan(se_18_34) else np.nan,
        },
        {
            "metric": "Retirement cliff gap (pct 55+ minus pct 18-34)",
            "value": cliff_gap,
            "SE": se_gap,
            "CI_95_lo": cliff_gap - 1.96 * se_gap if not np.isnan(se_gap) else np.nan,
            "CI_95_hi": cliff_gap + 1.96 * se_gap if not np.isnan(se_gap) else np.nan,
        },
        {
            "metric": "Pct 60+ (retiring within ~5 years)",
            "value": pct_60plus,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Weighted N aged 55-64",
            "value": n_55_64_wt,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Mean years to retirement (workers 45+, assuming age 65)",
            "value": mean_ytr,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
        {
            "metric": "Median years to retirement (workers 45+, assuming age 65)",
            "value": median_ytr,
            "SE": np.nan,
            "CI_95_lo": np.nan,
            "CI_95_hi": np.nan,
        },
    ]

    cliff_df = pd.DataFrame(rows)

    # Print key findings
    print(f"  55+ share: {pct_55plus:.1f}% (SE={se_55plus:.2f})")
    print(f"  18-34 share: {pct_18_34:.1f}% (SE={se_18_34:.2f})")
    if cliff_gap > 0:
        print(f"  Retirement cliff gap: +{cliff_gap:.1f} pp "
              f"(more workers near retirement than entering)")
    else:
        print(f"  Retirement cliff gap: {cliff_gap:.1f} pp "
              f"(pipeline exceeds near-retirees)")
    print(f"  Mean years to retirement (45+): {mean_ytr:.1f}")
    print(f"  Median years to retirement (45+): {median_ytr:.1f}")

    return cliff_df


def build_geographic_aging(df):
    """Requirement 3: State-level aging analysis for OCC=1530."""
    surveyors = df[df["OCC"] == 1530].copy()
    if len(surveyors) == 0:
        print("  WARNING: No OCC=1530 records for geographic analysis.")
        return pd.DataFrame()

    if "STATEFIP" not in surveyors.columns:
        print("  WARNING: STATEFIP not in data; skipping geographic analysis.")
        return pd.DataFrame()

    rows = []
    suppressed_count = 0

    for fip, state_name in sorted(STATEFIP_MAP.items(), key=lambda x: x[1]):
        state_df = surveyors[surveyors["STATEFIP"] == fip]
        n_unweighted = len(state_df)

        # Suppress states below minimum sample size
        if n_unweighted < MIN_STATE_N:
            suppressed_count += 1
            continue

        wt = state_df["PERWT"]
        total_wt = wt.sum()

        med_age = weighted_median(state_df["AGE"], wt)
        pct_55plus = weighted_share(state_df["AGE"] >= 55, wt)
        pct_18_34 = weighted_share(state_df["AGE"] <= 34, wt)
        pct_65plus = weighted_share(state_df["AGE"] >= 65, wt)

        # BRR SE for median age at state level
        has_repwts = all(c in state_df.columns for c in REPWT_COLS)
        if has_repwts and n_unweighted >= MIN_STATE_N:
            rep_medians = [
                weighted_median(state_df["AGE"], state_df[rc])
                for rc in REPWT_COLS
            ]
            se_med = brr_se(rep_medians, med_age)
        else:
            se_med = np.nan

        high_risk = pct_55plus >= 40.0

        rows.append({
            "STATEFIP": fip,
            "state": state_name,
            "unweighted_n": n_unweighted,
            "weighted_n": total_wt,
            "median_age": med_age,
            "median_age_SE": se_med,
            "pct_18_34": pct_18_34,
            "pct_55plus": pct_55plus,
            "pct_65plus": pct_65plus,
            "high_risk_flag": high_risk,
        })

    geo_df = pd.DataFrame(rows)

    if suppressed_count > 0:
        print(f"  Suppressed {suppressed_count} states with unweighted n < {MIN_STATE_N}")

    if len(geo_df) > 0:
        n_high_risk = geo_df["high_risk_flag"].sum()
        oldest = geo_df.loc[geo_df["median_age"].idxmax()]
        youngest = geo_df.loc[geo_df["median_age"].idxmin()]
        print(f"  {len(geo_df)} states reported "
              f"(range: {youngest['state']} {youngest['median_age']:.1f} "
              f"to {oldest['state']} {oldest['median_age']:.1f})")
        print(f"  {n_high_risk} states flagged as high-risk (55+ share >= 40%)")

    return geo_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 4A: AGING_ANALYSIS — Paper 1 age-distribution tables"
    )
    parser.add_argument(
        "--input", default="data/surveying_recoded.csv",
        help="Path to recoded person-level microdata (default: data/surveying_recoded.csv)",
    )
    parser.add_argument(
        "--benchmarks", default="data/benchmarks.csv",
        help="Path to benchmark comparison table (default: data/benchmarks.csv)",
    )
    parser.add_argument(
        "--outdir", default="analysis/p1",
        help="Output directory for Paper 1 tables (default: analysis/p1)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    bench_path = Path(args.benchmarks)
    outdir = Path(args.outdir)

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("Run s2_recode.py first.")
        sys.exit(1)

    print(f"Loading recoded microdata: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"  {len(df):,} person records loaded.")

    # Quick data summary
    for occ_code, label in [(1530, "Surveyors"), (1560, "Technicians"),
                            (1520, "Cartographers")]:
        n = (df["OCC"] == occ_code).sum()
        print(f"  OCC {occ_code} ({label}): {n:,} unweighted")

    # Verify replicate weights exist
    repwt_present = [c for c in REPWT_COLS if c in df.columns]
    if len(repwt_present) < N_REPS:
        missing_n = N_REPS - len(repwt_present)
        print(f"  WARNING: {missing_n} replicate weights missing. "
              f"BRR SE will use {len(repwt_present)} replicates available.")
        if len(repwt_present) == 0:
            print("  CRITICAL: No replicate weights found. "
                  "SE and CI columns will be NaN.")
    else:
        print(f"  All {N_REPS} replicate weights present.")

    # Load benchmarks
    benchmarks_df = None
    if bench_path.exists():
        print(f"\nLoading benchmarks: {bench_path}")
        benchmarks_df = pd.read_csv(bench_path)
        print(f"  {len(benchmarks_df)} benchmark groups loaded: "
              f"{list(benchmarks_df['group'])}")
    else:
        print(f"\nWARNING: Benchmarks file not found: {bench_path}")
        print("  Age distribution table will include only surveying occupations.")

    # ------------------------------------------------------------------
    # Create output directory
    # ------------------------------------------------------------------
    outdir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1 + 4. Age distribution / benchmark comparison table
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("AGE DISTRIBUTION & BENCHMARK COMPARISON")
    print("=" * 65)
    age_table = build_age_distribution_table(df, benchmarks_df)

    out_age = outdir / "p1_age_distribution.csv"
    age_table.to_csv(out_age, index=False)
    print(f"\n  -> Saved: {out_age}  ({len(age_table)} rows)")

    # ------------------------------------------------------------------
    # 2. Retirement cliff projection
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("RETIREMENT CLIFF PROJECTION (OCC=1530 Surveyors)")
    print("=" * 65)
    cliff_table = build_retirement_cliff(df)

    out_cliff = outdir / "p1_retirement_cliff.csv"
    if len(cliff_table) > 0:
        cliff_table.to_csv(out_cliff, index=False)
        print(f"\n  -> Saved: {out_cliff}  ({len(cliff_table)} rows)")
    else:
        print("  No retirement cliff table produced (no data).")

    # ------------------------------------------------------------------
    # 3. Geographic variation
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("GEOGRAPHIC AGING (OCC=1530 Surveyors by state)")
    print("=" * 65)
    geo_table = build_geographic_aging(df)

    out_geo = outdir / "p1_geographic_aging.csv"
    if len(geo_table) > 0:
        geo_table.to_csv(out_geo, index=False)
        print(f"\n  -> Saved: {out_geo}  ({len(geo_table)} rows)")
    else:
        print("  No geographic table produced (no data or STATEFIP missing).")

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("PAPER 1 AGING ANALYSIS COMPLETE")
    print("=" * 65)
    print(f"  Output directory: {outdir}")
    print(f"  Files produced:")
    for f in sorted(outdir.glob("p1_*.csv")):
        size_kb = f.stat().st_size / 1024
        print(f"    {f.name}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
