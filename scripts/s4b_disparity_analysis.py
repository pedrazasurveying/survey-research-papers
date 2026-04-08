"""
Subagent 4B: DISPARITY_ANALYSIS
=================================
Compute all demographic composition analyses for Paper 2
(Demographic Disparity and Earnings Gaps in the U.S. Land Surveying Workforce).

Reads person-level ACS microdata (from s2_recode.py) and benchmark data
(from s3_benchmark_build.py). Produces weighted proportions with BRR standard
errors, Rao-Scott chi-square tests, representation ratios, and intersectional
cross-tabulations.

Usage:
    python scripts/s4b_disparity_analysis.py
    python scripts/s4b_disparity_analysis.py --input data/surveying_recoded.csv --benchmarks data/benchmarks.csv --outdir analysis/p2
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPWT_COLS = [f"REPWTP{i}" for i in range(1, 81)]
FAY_K = 0.5
FAY_FACTOR = 1.0 / (len(REPWT_COLS) * (1 - FAY_K) ** 2)  # 1/(80*0.25) = 0.05

# Minimum unweighted cell size for reporting
MIN_CELL_N = 50

# Variables for composition analysis
COMP_VARS = ["race_eth", "sex_r", "educ_r", "agegroup", "veteran"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def weighted_proportion(df, var, weight_col="PERWT"):
    """Compute weighted proportions for each category of var."""
    total_wt = df[weight_col].sum()
    if total_wt == 0:
        return pd.Series(dtype=float)
    props = df.groupby(var)[weight_col].sum() / total_wt
    return props


def brr_se_proportion(df, var, weight_col="PERWT"):
    """
    Compute BRR standard errors for weighted proportions using Fay k=0.5 method.

    SE = sqrt( FAY_FACTOR * sum_{r=1}^{80} (rep_est_r - full_est)^2 )
    """
    full_est = weighted_proportion(df, var, weight_col)
    categories = full_est.index

    squared_diffs = pd.DataFrame(0.0, index=categories, columns=range(len(REPWT_COLS)))

    for r, repwt in enumerate(REPWT_COLS):
        if repwt not in df.columns:
            continue
        rep_est = weighted_proportion(df, var, repwt)
        for cat in categories:
            diff = rep_est.get(cat, 0.0) - full_est[cat]
            squared_diffs.loc[cat, r] = diff ** 2

    se = np.sqrt(FAY_FACTOR * squared_diffs.sum(axis=1))
    return se


def build_composition_table(df, var, occ_label, weight_col="PERWT"):
    """Build a composition table with proportions, SE, CI, and unweighted n."""
    props = weighted_proportion(df, var, weight_col)
    se = brr_se_proportion(df, var, weight_col)
    counts = df.groupby(var).size()

    rows = []
    for cat in props.index:
        p = props[cat]
        s = se.get(cat, np.nan)
        n = counts.get(cat, 0)
        rows.append({
            "occupation": occ_label,
            "variable": var,
            "category": cat,
            "weighted_pct": round(p * 100, 2),
            "se": round(s * 100, 4),
            "ci_lower": round(max(0, (p - 1.96 * s)) * 100, 2),
            "ci_upper": round(min(1, (p + 1.96 * s)) * 100, 2),
            "unweighted_n": n,
        })
    return pd.DataFrame(rows)


def rao_scott_chi2(df_a, df_b, var, label_a="Surveyors", label_b="Technicians"):
    """
    Approximate Rao-Scott chi-square comparing composition on var between
    two occupation groups. Uses scipy chi2_contingency as approximation.

    Note: This is a design-based approximation. For fully correct Rao-Scott,
    a survey-aware package (e.g., R survey::svychisq) would be needed.
    """
    wt_a = df_a.groupby(var)["PERWT"].sum()
    wt_b = df_b.groupby(var)["PERWT"].sum()

    # Align categories
    all_cats = sorted(set(wt_a.index) | set(wt_b.index))
    table = np.array([
        [wt_a.get(cat, 0) for cat in all_cats],
        [wt_b.get(cat, 0) for cat in all_cats],
    ])

    # Remove columns with all zeros
    nonzero = table.sum(axis=0) > 0
    table = table[:, nonzero]
    cats_used = [c for c, nz in zip(all_cats, nonzero) if nz]

    if table.shape[1] < 2:
        return None

    chi2, p, dof, expected = chi2_contingency(table)
    return {
        "variable": var,
        "comparison": f"{label_a} vs {label_b}",
        "chi2": round(chi2, 2),
        "dof": dof,
        "p_value": p,
        "note": "Approximation using scipy chi2_contingency on weighted counts"
    }


# ---------------------------------------------------------------------------
# Main analysis functions
# ---------------------------------------------------------------------------
def analyze_composition(df, benchmarks):
    """Weighted proportions by demographic variables for OCC=1530 and OCC=1560."""
    print("\n[1/7] Computing demographic composition...")

    surveyors = df[df["OCC"] == 1530].copy()
    technicians = df[df["OCC"] == 1560].copy()

    tables = []
    chi2_results = []

    for var in COMP_VARS:
        for sub, label in [(surveyors, "Surveyors"), (technicians, "Technicians")]:
            tbl = build_composition_table(sub, var, label)
            tables.append(tbl)

        # Rao-Scott chi-square comparison
        result = rao_scott_chi2(surveyors, technicians, var)
        if result:
            chi2_results.append(result)
            sig = "***" if result["p_value"] < 0.001 else "**" if result["p_value"] < 0.01 else "*" if result["p_value"] < 0.05 else "n.s."
            print(f"  {var}: chi2={result['chi2']:.1f}, p={result['p_value']:.4f} {sig}")

    composition = pd.concat(tables, ignore_index=True)

    # Append chi-square results as separate rows at the bottom
    chi2_df = pd.DataFrame(chi2_results)

    print(f"  Composition table: {len(composition)} rows")
    return composition, chi2_df


def analyze_representation_ratios(df, benchmarks):
    """Compute representation ratios vs U.S. workforce benchmarks."""
    print("\n[2/7] Computing representation ratios...")

    surveyors = df[df["OCC"] == 1530]

    # Get U.S. workforce benchmark row
    us_bench = benchmarks[benchmarks["group"] == "U.S. workforce"]
    if len(us_bench) == 0:
        print("  WARNING: No 'U.S. workforce' row in benchmarks. Skipping ratios.")
        return pd.DataFrame()

    us_bench = us_bench.iloc[0]

    # Surveyor proportions
    total_wt = surveyors["PERWT"].sum()
    if total_wt == 0:
        return pd.DataFrame()

    # Map from surveyor category labels to benchmark column names
    ratio_map = {
        ("sex_r", "Female"): "pct_female",
        ("sex_r", "Male"): "pct_male",
        ("race_eth", "NH White"): "pct_NH_White",
        ("race_eth", "NH Black"): "pct_NH_Black",
        ("race_eth", "Hispanic"): "pct_Hispanic",
        ("race_eth", "NH Asian"): "pct_NH_Asian",
        ("veteran", "Veteran"): "pct_veteran",
    }

    rows = []
    for (var, cat), bench_col in ratio_map.items():
        mask = surveyors[var] == cat
        surv_pct = surveyors.loc[mask, "PERWT"].sum() / total_wt * 100
        bench_pct = us_bench.get(bench_col, np.nan)

        if pd.isna(bench_pct) or bench_pct == 0:
            ratio = np.nan
        else:
            ratio = surv_pct / bench_pct

        flag = ""
        if not np.isna(ratio) and ratio < 0.5:
            flag = "SEVERE UNDERREPRESENTATION"
        elif not np.isna(ratio) and ratio < 0.8:
            flag = "Underrepresentation"

        n_unweighted = mask.sum()
        rows.append({
            "variable": var,
            "category": cat,
            "surveyor_pct": round(surv_pct, 2),
            "us_workforce_pct": round(bench_pct, 2) if not pd.isna(bench_pct) else np.nan,
            "representation_ratio": round(ratio, 3) if not np.isna(ratio) else np.nan,
            "flag": flag,
            "unweighted_n": n_unweighted,
        })

        if flag:
            print(f"  {cat}: ratio={ratio:.2f} -- {flag}")

    return pd.DataFrame(rows)


def analyze_intersectional(df):
    """Race/ethnicity x sex cross-tab for OCC=1530. Suppress cells n < 50."""
    print("\n[3/7] Computing intersectional analysis (race x sex)...")

    surveyors = df[df["OCC"] == 1530].copy()
    total_wt = surveyors["PERWT"].sum()

    # Unweighted counts
    ct_unweighted = pd.crosstab(surveyors["race_eth"], surveyors["sex_r"])

    # Weighted counts
    ct_weighted = surveyors.groupby(["race_eth", "sex_r"])["PERWT"].sum().unstack(fill_value=0)

    rows = []
    for race in ct_unweighted.index:
        for sex in ct_unweighted.columns:
            n = ct_unweighted.loc[race, sex] if (race in ct_unweighted.index and sex in ct_unweighted.columns) else 0
            wt = ct_weighted.loc[race, sex] if (race in ct_weighted.index and sex in ct_weighted.columns) else 0

            if n < MIN_CELL_N:
                rows.append({
                    "race_eth": race,
                    "sex_r": sex,
                    "weighted_n": np.nan,
                    "weighted_pct": np.nan,
                    "unweighted_n": n,
                    "suppressed": True,
                })
            else:
                rows.append({
                    "race_eth": race,
                    "sex_r": sex,
                    "weighted_n": round(wt, 0),
                    "weighted_pct": round(wt / total_wt * 100, 2),
                    "unweighted_n": n,
                    "suppressed": False,
                })

    result = pd.DataFrame(rows)
    n_suppressed = result["suppressed"].sum()
    print(f"  {len(result)} cells, {n_suppressed} suppressed (n < {MIN_CELL_N})")
    return result


def analyze_educ_by_race(df):
    """Education pathway by race/ethnicity within OCC=1530."""
    print("\n[4/7] Computing education by race/ethnicity...")

    surveyors = df[df["OCC"] == 1530].copy()

    rows = []
    for race in sorted(surveyors["race_eth"].unique()):
        sub = surveyors[surveyors["race_eth"] == race]
        n_total = len(sub)
        wt_total = sub["PERWT"].sum()

        if n_total < MIN_CELL_N:
            print(f"  {race}: n={n_total} < {MIN_CELL_N}, suppressing entire group")
            continue

        for educ in ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]:
            mask = sub["educ_r"] == educ
            n = mask.sum()
            wt = sub.loc[mask, "PERWT"].sum()

            rows.append({
                "race_eth": race,
                "educ_r": educ,
                "weighted_pct": round(wt / wt_total * 100, 2) if wt_total > 0 else np.nan,
                "weighted_n": round(wt, 0),
                "unweighted_n": n,
                "group_total_n": n_total,
            })

    result = pd.DataFrame(rows)
    print(f"  {len(result)} rows")

    # Print key finding: education gap
    for race in result["race_eth"].unique():
        ba_pct = result.loc[(result["race_eth"] == race) & (result["educ_r"] == "BA or BS"), "weighted_pct"]
        if len(ba_pct) > 0:
            print(f"  {race} BA/BS: {ba_pct.values[0]:.1f}%")

    return result


def analyze_age_by_race(df):
    """Age distribution by race/ethnicity within OCC=1530."""
    print("\n[5/7] Computing age distribution by race/ethnicity...")

    surveyors = df[df["OCC"] == 1530].copy()

    rows = []
    for race in sorted(surveyors["race_eth"].unique()):
        sub = surveyors[surveyors["race_eth"] == race]
        n_total = len(sub)
        wt_total = sub["PERWT"].sum()

        if n_total < MIN_CELL_N:
            continue

        # Weighted median age
        ages = sub["AGE"].values
        weights = sub["PERWT"].values
        sorted_idx = np.argsort(ages)
        cumwt = np.cumsum(weights[sorted_idx])
        median_age = ages[sorted_idx][np.searchsorted(cumwt, cumwt[-1] / 2)]

        # Pct under 35 and over 55
        pct_under35 = sub.loc[sub["AGE"] < 35, "PERWT"].sum() / wt_total * 100
        pct_55plus = sub.loc[sub["AGE"] >= 55, "PERWT"].sum() / wt_total * 100

        for ag in ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]:
            mask = sub["agegroup"] == ag
            wt = sub.loc[mask, "PERWT"].sum()
            rows.append({
                "race_eth": race,
                "agegroup": ag,
                "weighted_pct": round(wt / wt_total * 100, 2) if wt_total > 0 else np.nan,
                "unweighted_n": mask.sum(),
            })

        # Summary row
        rows.append({
            "race_eth": race,
            "agegroup": "SUMMARY",
            "weighted_pct": np.nan,
            "unweighted_n": n_total,
            "median_age": median_age,
            "pct_under_35": round(pct_under35, 2),
            "pct_55_plus": round(pct_55plus, 2),
        })

    result = pd.DataFrame(rows)
    print(f"  {len(result)} rows")

    # Key finding: are minorities younger?
    summaries = result[result["agegroup"] == "SUMMARY"].copy()
    if len(summaries) > 0:
        print("  Median ages by race/ethnicity:")
        for _, row in summaries.iterrows():
            if "median_age" in row and not pd.isna(row.get("median_age")):
                print(f"    {row['race_eth']}: {row['median_age']:.0f}")

    return result


def analyze_veteran(df, benchmarks):
    """Veteran representation within surveying vs benchmark groups."""
    print("\n[6/7] Computing veteran representation...")

    rows = []
    for occ_code, label in [(1530, "Surveyors"), (1560, "Technicians")]:
        sub = df[df["OCC"] == occ_code]
        valid = sub[sub["veteran"].isin(["Veteran", "Non-veteran"])]
        if len(valid) == 0:
            continue

        wt_total = valid["PERWT"].sum()
        vet_mask = valid["veteran"] == "Veteran"
        vet_pct = valid.loc[vet_mask, "PERWT"].sum() / wt_total * 100

        # BRR SE for veteran proportion
        full_est = vet_pct / 100
        sq_diffs = 0.0
        for repwt in REPWT_COLS:
            if repwt not in valid.columns:
                continue
            rep_total = valid[repwt].sum()
            if rep_total > 0:
                rep_est = valid.loc[vet_mask, repwt].sum() / rep_total
            else:
                rep_est = 0
            sq_diffs += (rep_est - full_est) ** 2

        se = np.sqrt(FAY_FACTOR * sq_diffs) * 100

        rows.append({
            "group": label,
            "pct_veteran": round(vet_pct, 2),
            "se": round(se, 4),
            "ci_lower": round(max(0, vet_pct - 1.96 * se), 2),
            "ci_upper": round(min(100, vet_pct + 1.96 * se), 2),
            "unweighted_n_veteran": vet_mask.sum(),
            "unweighted_n_total": len(valid),
        })
        print(f"  {label}: {vet_pct:.1f}% veteran (SE={se:.2f})")

    # Add benchmark groups
    for _, brow in benchmarks.iterrows():
        if "pct_veteran" in brow and not pd.isna(brow["pct_veteran"]):
            rows.append({
                "group": brow["group"] + " (benchmark)",
                "pct_veteran": round(brow["pct_veteran"], 2),
                "se": np.nan,
                "ci_lower": np.nan,
                "ci_upper": np.nan,
                "unweighted_n_veteran": np.nan,
                "unweighted_n_total": np.nan,
            })

    return pd.DataFrame(rows)


def analyze_self_employment(df):
    """Self-employment rates by race/ethnicity. Confirmed scope addition S8."""
    print("\n[7/7] Computing self-employment rates by race/ethnicity...")

    surveyors = df[df["OCC"] == 1530].copy()
    total_wt = surveyors["PERWT"].sum()

    rows = []
    for race in sorted(surveyors["race_eth"].unique()):
        sub = surveyors[surveyors["race_eth"] == race]
        n_total = len(sub)
        wt_total = sub["PERWT"].sum()

        if n_total < MIN_CELL_N:
            print(f"  {race}: n={n_total} < {MIN_CELL_N}, suppressing")
            continue

        se_mask = sub["classwkr_r"] == "Self-employed"
        se_n = se_mask.sum()
        se_pct = sub.loc[se_mask, "PERWT"].sum() / wt_total * 100 if wt_total > 0 else np.nan

        # BRR SE
        full_est = se_pct / 100
        sq_diffs = 0.0
        for repwt in REPWT_COLS:
            if repwt not in sub.columns:
                continue
            rep_total = sub[repwt].sum()
            if rep_total > 0:
                rep_est = sub.loc[se_mask, repwt].sum() / rep_total
            else:
                rep_est = 0
            sq_diffs += (rep_est - full_est) ** 2

        se_err = np.sqrt(FAY_FACTOR * sq_diffs) * 100

        rows.append({
            "race_eth": race,
            "pct_self_employed": round(se_pct, 2),
            "se": round(se_err, 4),
            "ci_lower": round(max(0, se_pct - 1.96 * se_err), 2),
            "ci_upper": round(min(100, se_pct + 1.96 * se_err), 2),
            "unweighted_n_self_emp": se_n,
            "unweighted_n_total": n_total,
        })
        print(f"  {race}: {se_pct:.1f}% self-employed (n={se_n})")

    # Also compute overall by class of worker
    print("  Overall class-of-worker distribution (Surveyors):")
    for cls in ["Private wage/salary", "Government", "Self-employed"]:
        mask = surveyors["classwkr_r"] == cls
        pct = surveyors.loc[mask, "PERWT"].sum() / total_wt * 100
        print(f"    {cls}: {pct:.1f}%")

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 4B: DISPARITY_ANALYSIS — demographic composition for Paper 2"
    )
    parser.add_argument("--input", default="data/surveying_recoded.csv",
                        help="Path to recoded survey data (from s2_recode.py)")
    parser.add_argument("--benchmarks", default="data/benchmarks.csv",
                        help="Path to benchmark data (from s3_benchmark_build.py)")
    parser.add_argument("--outdir", default="analysis/p2",
                        help="Output directory for results")
    args = parser.parse_args()

    input_path = Path(args.input)
    bench_path = Path(args.benchmarks)
    outdir = Path(args.outdir)

    # Validate inputs
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("Run s2_recode.py first.")
        sys.exit(1)

    if not bench_path.exists():
        print(f"ERROR: Benchmarks file not found: {bench_path}")
        print("Run s3_benchmark_build.py first.")
        sys.exit(1)

    outdir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading recoded data: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"  {len(df):,} rows loaded.")

    print(f"Loading benchmarks: {bench_path}")
    benchmarks = pd.read_csv(bench_path)
    print(f"  {len(benchmarks)} benchmark groups loaded.")

    # Check for replicate weights
    repwt_present = [c for c in REPWT_COLS if c in df.columns]
    if len(repwt_present) < 80:
        print(f"WARNING: Only {len(repwt_present)}/80 replicate weights found.")
        print("  BRR standard errors may be inaccurate.")

    # Quick summary
    for occ_code, label in [(1530, "Surveyors"), (1560, "Technicians"), (1520, "Cartographers")]:
        n = (df["OCC"] == occ_code).sum()
        print(f"  OCC {occ_code} ({label}): n={n:,}")

    print("\n" + "=" * 70)
    print("PAPER 2: DEMOGRAPHIC DISPARITY ANALYSIS")
    print("=" * 70)

    # 1. Composition
    composition, chi2_results = analyze_composition(df, benchmarks)
    composition.to_csv(outdir / "p2_composition.csv", index=False)
    if len(chi2_results) > 0:
        # Append chi2 results to composition file as a note, and also print
        chi2_results.to_csv(outdir / "p2_composition_chi2.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_composition.csv")

    # 2. Representation ratios
    ratios = analyze_representation_ratios(df, benchmarks)
    ratios.to_csv(outdir / "p2_representation_ratios.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_representation_ratios.csv")

    # 3. Intersectional
    intersectional = analyze_intersectional(df)
    intersectional.to_csv(outdir / "p2_intersectional.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_intersectional.csv")

    # 4. Education by race
    educ_by_race = analyze_educ_by_race(df)
    educ_by_race.to_csv(outdir / "p2_educ_by_race.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_educ_by_race.csv")

    # 5. Age by race
    age_by_race = analyze_age_by_race(df)
    age_by_race.to_csv(outdir / "p2_age_by_race.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_age_by_race.csv")

    # 6. Veteran
    veteran = analyze_veteran(df, benchmarks)
    veteran.to_csv(outdir / "p2_veteran.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_veteran.csv")

    # 7. Self-employment
    self_emp = analyze_self_employment(df)
    self_emp.to_csv(outdir / "p2_self_employment.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_self_employment.csv")

    print("\n" + "=" * 70)
    print("DISPARITY ANALYSIS COMPLETE")
    print(f"All outputs saved to: {outdir}/")
    print("=" * 70)

    # Print key summary findings
    print("\nKEY FINDINGS SUMMARY:")

    # Representation ratios
    if len(ratios) > 0:
        severe = ratios[ratios["flag"] == "SEVERE UNDERREPRESENTATION"]
        if len(severe) > 0:
            print("\n  Severe underrepresentation (ratio < 0.5):")
            for _, row in severe.iterrows():
                print(f"    {row['category']}: {row['surveyor_pct']:.1f}% vs "
                      f"{row['us_workforce_pct']:.1f}% U.S. workforce "
                      f"(ratio={row['representation_ratio']:.2f})")

    # Intersectional
    if len(intersectional) > 0:
        non_suppressed = intersectional[~intersectional["suppressed"]]
        if len(non_suppressed) > 0:
            female = non_suppressed[non_suppressed["sex_r"] == "Female"]
            if len(female) > 0:
                total_female_pct = female["weighted_pct"].sum()
                print(f"\n  Total female share (Surveyors): {total_female_pct:.1f}%")


if __name__ == "__main__":
    main()
