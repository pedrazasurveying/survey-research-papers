"""
Subagent 4C: EARNINGS_ANALYSIS
================================
Compute all earnings disparity analyses for Paper 2
(Demographic Disparity and Earnings Gaps in the U.S. Land Surveying Workforce).

Computes weighted median wages with BRR standard errors (Woodruff method),
gender and racial wage gaps, intersectional earnings, education-controlled
comparisons, and OLS regression of log(hourly_wage).

Usage:
    python scripts/s4c_earnings_analysis.py
    python scripts/s4c_earnings_analysis.py --input data/surveying_recoded.csv --outdir analysis/p2
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Suppress convergence warnings from statsmodels during fixed-effects estimation
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPWT_COLS = [f"REPWTP{i}" for i in range(1, 81)]
FAY_K = 0.5
FAY_FACTOR = 1.0 / (len(REPWT_COLS) * (1 - FAY_K) ** 2)

MIN_CELL_N = 50


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def weighted_median(values, weights):
    """Compute weighted median. Returns NaN if inputs are empty."""
    mask = values.notna() & weights.notna() & (weights > 0) & values.notna()
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


def brr_se_median(df, value_col, weight_col="PERWT"):
    """
    BRR standard error for a weighted median using the Woodruff method.

    Computes median from each replicate weight set, then:
    SE = sqrt( FAY_FACTOR * sum( (rep_median - full_median)^2 ) )
    """
    values = df[value_col]
    full_median = weighted_median(values, df[weight_col])

    sq_diffs = 0.0
    for repwt in REPWT_COLS:
        if repwt not in df.columns:
            continue
        rep_median = weighted_median(values, df[repwt])
        if not np.isnan(rep_median) and not np.isnan(full_median):
            sq_diffs += (rep_median - full_median) ** 2

    se = np.sqrt(FAY_FACTOR * sq_diffs)
    return full_median, se


def compute_group_median(df, value_col, group_label, weight_col="PERWT"):
    """Compute weighted median with BRR SE and 95% CI for a group."""
    valid = df[df[value_col].notna()].copy()
    n = len(valid)

    if n < MIN_CELL_N:
        return {
            "group": group_label,
            "median": np.nan,
            "se": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "unweighted_n": n,
            "suppressed": True,
        }

    median_val, se = brr_se_median(valid, value_col, weight_col)

    return {
        "group": group_label,
        "median": round(median_val, 0),
        "se": round(se, 2),
        "ci_lower": round(median_val - 1.96 * se, 0),
        "ci_upper": round(median_val + 1.96 * se, 0),
        "unweighted_n": n,
        "suppressed": False,
    }


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------
def analyze_core_earnings(df):
    """Weighted median wage_adj and hourly_wage by occupation with BRR SE/CI."""
    print("\n[1/6] Computing core earnings by occupation...")

    rows = []
    for occ_code, label in [(1310, "Surveyors"), (1560, "Technicians")]:
        sub = df[df["OCC"] == occ_code]

        # Annual wage
        annual = compute_group_median(sub, "wage_adj", f"{label} (annual)", "PERWT")
        annual["measure"] = "wage_adj"
        annual["occ_code"] = occ_code
        rows.append(annual)

        # Hourly wage
        hourly = compute_group_median(sub, "hourly_wage", f"{label} (hourly)", "PERWT")
        hourly["measure"] = "hourly_wage"
        hourly["occ_code"] = occ_code
        rows.append(hourly)

        print(f"  {label}: annual median=${annual['median']:,.0f} (SE=${annual['se']:,.0f}), "
              f"hourly median=${hourly['median']:,.2f} (SE=${hourly['se']:.2f})"
              if not annual['suppressed'] else f"  {label}: suppressed")

    return pd.DataFrame(rows)


def analyze_wage_gaps(df):
    """Gender and racial wage gaps within OCC=1310 and OCC=1560."""
    print("\n[2/6] Computing wage gaps...")

    rows = []

    for occ_code, label in [(1310, "Surveyors"), (1560, "Technicians")]:
        sub = df[df["OCC"] == occ_code]

        # --- Gender wage gap ---
        print(f"\n  {label} — Gender wage gap:")
        male_sub = sub[sub["sex_r"] == "Male"]
        female_sub = sub[sub["sex_r"] == "Female"]

        male_med, male_se = brr_se_median(male_sub[male_sub["wage_adj"].notna()], "wage_adj")
        female_n = len(female_sub[female_sub["wage_adj"].notna()])

        if female_n >= MIN_CELL_N:
            female_med, female_se = brr_se_median(female_sub[female_sub["wage_adj"].notna()], "wage_adj")

            gap_dollars = male_med - female_med
            gap_pct = (gap_dollars / male_med) * 100 if male_med > 0 else np.nan

            # SE of gap (approximation: sqrt of sum of squared SEs)
            gap_se = np.sqrt(male_se ** 2 + female_se ** 2)

            rows.append({
                "occupation": label,
                "comparison": "Gender (Male - Female)",
                "measure": "wage_adj",
                "group_a": "Male",
                "group_a_median": round(male_med, 0),
                "group_a_se": round(male_se, 2),
                "group_a_n": len(male_sub[male_sub["wage_adj"].notna()]),
                "group_b": "Female",
                "group_b_median": round(female_med, 0),
                "group_b_se": round(female_se, 2),
                "group_b_n": female_n,
                "gap_dollars": round(gap_dollars, 0),
                "gap_pct": round(gap_pct, 1),
                "gap_se": round(gap_se, 2),
                "gap_ci_lower": round(gap_dollars - 1.96 * gap_se, 0),
                "gap_ci_upper": round(gap_dollars + 1.96 * gap_se, 0),
                "suppressed": False,
            })
            print(f"    Male median: ${male_med:,.0f}")
            print(f"    Female median: ${female_med:,.0f}")
            print(f"    Gap: ${gap_dollars:,.0f} ({gap_pct:.1f}%)")
        else:
            print(f"    Female n={female_n} < {MIN_CELL_N}, suppressed")
            rows.append({
                "occupation": label,
                "comparison": "Gender (Male - Female)",
                "measure": "wage_adj",
                "group_a": "Male",
                "group_a_median": round(male_med, 0),
                "group_a_se": round(male_se, 2),
                "group_a_n": len(male_sub[male_sub["wage_adj"].notna()]),
                "group_b": "Female",
                "group_b_median": np.nan,
                "group_b_se": np.nan,
                "group_b_n": female_n,
                "gap_dollars": np.nan,
                "gap_pct": np.nan,
                "gap_se": np.nan,
                "gap_ci_lower": np.nan,
                "gap_ci_upper": np.nan,
                "suppressed": True,
            })

    # --- Racial wage gaps (OCC=1310 only, NH White as reference) ---
    print(f"\n  Surveyors — Racial wage gaps (ref: NH White):")
    surveyors = df[df["OCC"] == 1310]
    white_sub = surveyors[(surveyors["race_eth"] == "NH White") & surveyors["wage_adj"].notna()]
    white_med, white_se = brr_se_median(white_sub, "wage_adj")
    print(f"    NH White median: ${white_med:,.0f}")

    for race in sorted(surveyors["race_eth"].unique()):
        if race == "NH White":
            continue
        race_sub = surveyors[(surveyors["race_eth"] == race) & surveyors["wage_adj"].notna()]
        n = len(race_sub)

        if n < MIN_CELL_N:
            print(f"    {race}: n={n} < {MIN_CELL_N}, suppressed")
            rows.append({
                "occupation": "Surveyors",
                "comparison": f"Race (NH White - {race})",
                "measure": "wage_adj",
                "group_a": "NH White",
                "group_a_median": round(white_med, 0),
                "group_a_se": round(white_se, 2),
                "group_a_n": len(white_sub),
                "group_b": race,
                "group_b_median": np.nan,
                "group_b_se": np.nan,
                "group_b_n": n,
                "gap_dollars": np.nan,
                "gap_pct": np.nan,
                "gap_se": np.nan,
                "gap_ci_lower": np.nan,
                "gap_ci_upper": np.nan,
                "suppressed": True,
            })
            continue

        race_med, race_se = brr_se_median(race_sub, "wage_adj")
        gap_dollars = white_med - race_med
        gap_pct = (gap_dollars / white_med) * 100 if white_med > 0 else np.nan
        gap_se = np.sqrt(white_se ** 2 + race_se ** 2)

        rows.append({
            "occupation": "Surveyors",
            "comparison": f"Race (NH White - {race})",
            "measure": "wage_adj",
            "group_a": "NH White",
            "group_a_median": round(white_med, 0),
            "group_a_se": round(white_se, 2),
            "group_a_n": len(white_sub),
            "group_b": race,
            "group_b_median": round(race_med, 0),
            "group_b_se": round(race_se, 2),
            "group_b_n": n,
            "gap_dollars": round(gap_dollars, 0),
            "gap_pct": round(gap_pct, 1),
            "gap_se": round(gap_se, 2),
            "gap_ci_lower": round(gap_dollars - 1.96 * gap_se, 0),
            "gap_ci_upper": round(gap_dollars + 1.96 * gap_se, 0),
            "suppressed": False,
        })
        print(f"    {race}: ${race_med:,.0f} (gap=${gap_dollars:,.0f}, {gap_pct:.1f}%)")

    # --- Veteran wage comparison (OCC=1310) ---
    print(f"\n  Surveyors — Veteran wage comparison:")
    for vet_status in ["Veteran", "Non-veteran"]:
        vet_sub = surveyors[(surveyors["veteran"] == vet_status) & surveyors["wage_adj"].notna()]
        n = len(vet_sub)
        if n >= MIN_CELL_N:
            med, se = brr_se_median(vet_sub, "wage_adj")
            rows.append({
                "occupation": "Surveyors",
                "comparison": f"Veteran ({vet_status})",
                "measure": "wage_adj",
                "group_a": vet_status,
                "group_a_median": round(med, 0),
                "group_a_se": round(se, 2),
                "group_a_n": n,
                "group_b": np.nan,
                "group_b_median": np.nan,
                "group_b_se": np.nan,
                "group_b_n": np.nan,
                "gap_dollars": np.nan,
                "gap_pct": np.nan,
                "gap_se": np.nan,
                "gap_ci_lower": np.nan,
                "gap_ci_upper": np.nan,
                "suppressed": False,
            })
            print(f"    {vet_status}: ${med:,.0f}")
        else:
            print(f"    {vet_status}: n={n} < {MIN_CELL_N}, suppressed")

    # --- Intersectional earnings (race x sex, OCC=1310) ---
    print(f"\n  Surveyors — Intersectional earnings (race x sex):")
    for race in sorted(surveyors["race_eth"].unique()):
        for sex in ["Male", "Female"]:
            cell = surveyors[
                (surveyors["race_eth"] == race) &
                (surveyors["sex_r"] == sex) &
                surveyors["wage_adj"].notna()
            ]
            n = len(cell)
            if n >= MIN_CELL_N:
                med, se = brr_se_median(cell, "wage_adj")
                rows.append({
                    "occupation": "Surveyors",
                    "comparison": f"Intersectional ({race} x {sex})",
                    "measure": "wage_adj",
                    "group_a": f"{race} {sex}",
                    "group_a_median": round(med, 0),
                    "group_a_se": round(se, 2),
                    "group_a_n": n,
                    "group_b": np.nan,
                    "group_b_median": np.nan,
                    "group_b_se": np.nan,
                    "group_b_n": np.nan,
                    "gap_dollars": np.nan,
                    "gap_pct": np.nan,
                    "gap_se": np.nan,
                    "gap_ci_lower": np.nan,
                    "gap_ci_upper": np.nan,
                    "suppressed": False,
                })
                print(f"    {race} {sex}: ${med:,.0f} (n={n})")
            else:
                print(f"    {race} {sex}: n={n} < {MIN_CELL_N}, suppressed")

    # --- Education-controlled comparison (BA/BS holders only, OCC=1310) ---
    print(f"\n  Surveyors — Education-controlled (BA/BS holders only):")
    ba_surveyors = surveyors[surveyors["educ_r"] == "BA or BS"]

    # By sex
    for sex in ["Male", "Female"]:
        cell = ba_surveyors[(ba_surveyors["sex_r"] == sex) & ba_surveyors["wage_adj"].notna()]
        n = len(cell)
        if n >= MIN_CELL_N:
            med, se = brr_se_median(cell, "wage_adj")
            rows.append({
                "occupation": "Surveyors",
                "comparison": f"Educ-controlled BA/BS ({sex})",
                "measure": "wage_adj",
                "group_a": f"BA/BS {sex}",
                "group_a_median": round(med, 0),
                "group_a_se": round(se, 2),
                "group_a_n": n,
                "group_b": np.nan,
                "group_b_median": np.nan,
                "group_b_se": np.nan,
                "group_b_n": np.nan,
                "gap_dollars": np.nan,
                "gap_pct": np.nan,
                "gap_se": np.nan,
                "gap_ci_lower": np.nan,
                "gap_ci_upper": np.nan,
                "suppressed": False,
            })
            print(f"    BA/BS {sex}: ${med:,.0f} (n={n})")
        else:
            print(f"    BA/BS {sex}: n={n} < {MIN_CELL_N}, suppressed")

    # By race
    for race in sorted(ba_surveyors["race_eth"].unique()):
        cell = ba_surveyors[(ba_surveyors["race_eth"] == race) & ba_surveyors["wage_adj"].notna()]
        n = len(cell)
        if n >= MIN_CELL_N:
            med, se = brr_se_median(cell, "wage_adj")
            rows.append({
                "occupation": "Surveyors",
                "comparison": f"Educ-controlled BA/BS ({race})",
                "measure": "wage_adj",
                "group_a": f"BA/BS {race}",
                "group_a_median": round(med, 0),
                "group_a_se": round(se, 2),
                "group_a_n": n,
                "group_b": np.nan,
                "group_b_median": np.nan,
                "group_b_se": np.nan,
                "group_b_n": np.nan,
                "gap_dollars": np.nan,
                "gap_pct": np.nan,
                "gap_se": np.nan,
                "gap_ci_lower": np.nan,
                "gap_ci_upper": np.nan,
                "suppressed": False,
            })
            print(f"    BA/BS {race}: ${med:,.0f} (n={n})")
        else:
            print(f"    BA/BS {race}: n={n} < {MIN_CELL_N}, suppressed")

    return pd.DataFrame(rows)


def analyze_wage_regression(df):
    """
    OLS regression of log(hourly_wage) on demographic predictors within OCC=1310.

    Model: log(hourly_wage) ~ race_eth + sex_r + educ_r + agegroup + veteran
           + classwkr_r + STATEFIP (fixed effects)

    Uses statsmodels. Reports coefficients on race_eth and sex_r with SE and p-values.
    """
    print("\n[3/6] Running OLS wage regression (OCC=1310)...")

    try:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols as sm_ols
    except ImportError:
        print("  ERROR: statsmodels not installed. Skipping regression.")
        return pd.DataFrame()

    surveyors = df[df["OCC"] == 1310].copy()

    # Filter to valid observations
    valid = surveyors[
        surveyors["hourly_wage"].notna() &
        (surveyors["hourly_wage"] > 0) &
        surveyors["race_eth"].notna() &
        surveyors["sex_r"].notna() &
        surveyors["educ_r"].notna() &
        surveyors["agegroup"].notna() &
        surveyors["veteran"].notna() &
        surveyors["classwkr_r"].notna()
    ].copy()

    # Drop any Unknown/Other categories that may cause issues
    valid = valid[valid["educ_r"] != "Unknown"]
    valid = valid[valid["veteran"] != "N/A"]
    valid = valid[valid["classwkr_r"] != "Other/Unknown"]

    print(f"  Valid observations for regression: {len(valid):,}")

    if len(valid) < 100:
        print("  WARNING: Too few observations for regression. Skipping.")
        return pd.DataFrame()

    # Create log wage
    valid["log_hourly_wage"] = np.log(valid["hourly_wage"])

    # Check for STATEFIP
    has_statefip = "STATEFIP" in valid.columns
    if has_statefip:
        # Drop states with very small samples
        state_counts = valid.groupby("STATEFIP").size()
        small_states = state_counts[state_counts < 5].index
        if len(small_states) > 0:
            print(f"  Dropping {len(small_states)} states with n < 5 from FE estimation")
            valid = valid[~valid["STATEFIP"].isin(small_states)]
        valid["STATEFIP"] = valid["STATEFIP"].astype(str)

    # Create dummy variables manually for more control
    # Reference categories: NH White, Male, HS or less, 25-34, Non-veteran, Private
    y = valid["log_hourly_wage"].values

    # Build design matrix
    dummies = []
    dummy_names = []

    # Race/ethnicity (ref: NH White)
    for cat in sorted(valid["race_eth"].unique()):
        if cat == "NH White":
            continue
        d = (valid["race_eth"] == cat).astype(float).values
        if d.sum() >= 10:  # Need enough obs
            dummies.append(d)
            dummy_names.append(f"race_eth_{cat}")

    # Sex (ref: Male)
    for cat in sorted(valid["sex_r"].unique()):
        if cat == "Male":
            continue
        d = (valid["sex_r"] == cat).astype(float).values
        if d.sum() >= 10:
            dummies.append(d)
            dummy_names.append(f"sex_r_{cat}")

    # Education (ref: HS or less)
    educ_order = ["Some college or AA", "BA or BS", "Graduate degree"]
    for cat in educ_order:
        d = (valid["educ_r"] == cat).astype(float).values
        if d.sum() >= 10:
            dummies.append(d)
            dummy_names.append(f"educ_r_{cat}")

    # Age group (ref: 25-34)
    for cat in ["18-24", "35-44", "45-54", "55-64", "65+"]:
        d = (valid["agegroup"] == cat).astype(float).values
        if d.sum() >= 10:
            dummies.append(d)
            dummy_names.append(f"agegroup_{cat}")

    # Veteran (ref: Non-veteran)
    d = (valid["veteran"] == "Veteran").astype(float).values
    if d.sum() >= 10:
        dummies.append(d)
        dummy_names.append("veteran_Veteran")

    # Class of worker (ref: Private wage/salary)
    for cat in ["Government", "Self-employed"]:
        d = (valid["classwkr_r"] == cat).astype(float).values
        if d.sum() >= 10:
            dummies.append(d)
            dummy_names.append(f"classwkr_{cat}")

    # State fixed effects
    if has_statefip:
        state_vals = sorted(valid["STATEFIP"].unique())
        ref_state = state_vals[0]  # Use first state as reference
        for st in state_vals[1:]:
            d = (valid["STATEFIP"] == st).astype(float).values
            dummies.append(d)
            dummy_names.append(f"state_{st}")

    # Assemble X matrix with constant
    X = np.column_stack(dummies)
    X = sm.add_constant(X)
    col_names = ["const"] + dummy_names

    print(f"  Predictors: {len(dummy_names)} ({len([n for n in dummy_names if n.startswith('state_')])} state FE)")

    # Fit OLS
    try:
        model = sm.OLS(y, X).fit(cov_type="HC1")  # Robust SEs
        print(f"  R-squared: {model.rsquared:.4f}")
        print(f"  Adj R-squared: {model.rsquared_adj:.4f}")
        print(f"  N: {model.nobs:.0f}")
    except Exception as e:
        print(f"  ERROR fitting OLS: {e}")
        return pd.DataFrame()

    # Extract results — focus on race_eth and sex_r, but include all
    rows = []
    for i, name in enumerate(col_names):
        coef = model.params[i]
        se = model.bse[i]
        pval = model.pvalues[i]
        ci = model.conf_int()[i]

        # Determine variable group
        if name.startswith("race_eth_"):
            group = "race_eth"
        elif name.startswith("sex_r_"):
            group = "sex_r"
        elif name.startswith("educ_r_"):
            group = "educ_r"
        elif name.startswith("agegroup_"):
            group = "agegroup"
        elif name.startswith("veteran_"):
            group = "veteran"
        elif name.startswith("classwkr_"):
            group = "classwkr"
        elif name.startswith("state_"):
            group = "state_fe"
        else:
            group = "other"

        rows.append({
            "variable": name,
            "group": group,
            "coefficient": round(coef, 6),
            "se": round(se, 6),
            "t_stat": round(coef / se if se > 0 else np.nan, 3),
            "p_value": round(pval, 6),
            "ci_lower": round(ci[0], 6),
            "ci_upper": round(ci[1], 6),
        })

    result = pd.DataFrame(rows)

    # Print key coefficients
    print("\n  Key regression coefficients:")
    key_groups = ["race_eth", "sex_r"]
    for _, row in result[result["group"].isin(key_groups)].iterrows():
        sig = "***" if row["p_value"] < 0.001 else "**" if row["p_value"] < 0.01 else "*" if row["p_value"] < 0.05 else ""
        pct_effect = (np.exp(row["coefficient"]) - 1) * 100
        print(f"    {row['variable']}: {row['coefficient']:.4f} "
              f"(SE={row['se']:.4f}, p={row['p_value']:.4f}) {sig}")
        print(f"      -> {pct_effect:+.1f}% wage difference vs reference group")

    # Add model summary info
    summary_row = {
        "variable": "MODEL_SUMMARY",
        "group": "summary",
        "coefficient": np.nan,
        "se": np.nan,
        "t_stat": np.nan,
        "p_value": np.nan,
        "ci_lower": np.nan,
        "ci_upper": np.nan,
        "r_squared": round(model.rsquared, 6),
        "adj_r_squared": round(model.rsquared_adj, 6),
        "n_obs": int(model.nobs),
        "n_predictors": len(dummy_names),
        "f_statistic": round(model.fvalue, 4) if hasattr(model, "fvalue") and not np.isnan(model.fvalue) else np.nan,
        "f_pvalue": round(model.f_pvalue, 6) if hasattr(model, "f_pvalue") and not np.isnan(model.f_pvalue) else np.nan,
    }
    result = pd.concat([result, pd.DataFrame([summary_row])], ignore_index=True)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 4C: EARNINGS_ANALYSIS — earnings disparity for Paper 2"
    )
    parser.add_argument("--input", default="data/surveying_recoded.csv",
                        help="Path to recoded survey data (from s2_recode.py)")
    parser.add_argument("--outdir", default="analysis/p2",
                        help="Output directory for results")
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("Run s2_recode.py first.")
        sys.exit(1)

    outdir.mkdir(parents=True, exist_ok=True)

    # Load data
    print(f"Loading recoded data: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"  {len(df):,} rows loaded.")

    # Check replicate weights
    repwt_present = [c for c in REPWT_COLS if c in df.columns]
    if len(repwt_present) < 80:
        print(f"WARNING: Only {len(repwt_present)}/80 replicate weights found.")

    # Quick earnings summary
    for occ_code, label in [(1310, "Surveyors"), (1560, "Technicians")]:
        sub = df[df["OCC"] == occ_code]
        valid_wage = sub["wage_adj"].notna().sum()
        print(f"  {label}: {valid_wage:,} valid wage observations")

    print("\n" + "=" * 70)
    print("PAPER 2: EARNINGS ANALYSIS")
    print("=" * 70)

    # 1. Core earnings
    core = analyze_core_earnings(df)
    core.to_csv(outdir / "p2_earnings_core.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_earnings_core.csv")

    # 2. Wage gaps
    gaps = analyze_wage_gaps(df)
    gaps.to_csv(outdir / "p2_wage_gaps.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_wage_gaps.csv")

    # 3. Wage regression
    regression = analyze_wage_regression(df)
    regression.to_csv(outdir / "p2_wage_regression.csv", index=False)
    print(f"  -> Saved: {outdir}/p2_wage_regression.csv")

    print("\n" + "=" * 70)
    print("EARNINGS ANALYSIS COMPLETE")
    print(f"All outputs saved to: {outdir}/")
    print("=" * 70)

    # Summary
    print("\nKEY FINDINGS SUMMARY:")
    if len(gaps) > 0:
        gender_gaps = gaps[gaps["comparison"].str.contains("Gender") & ~gaps["suppressed"]]
        for _, row in gender_gaps.iterrows():
            print(f"  {row['occupation']} gender gap: ${row['gap_dollars']:,.0f} "
                  f"({row['gap_pct']:.1f}%)")

        racial_gaps = gaps[gaps["comparison"].str.contains("Race") & ~gaps["suppressed"]]
        for _, row in racial_gaps.iterrows():
            print(f"  {row['comparison']}: ${row['gap_dollars']:,.0f} "
                  f"({row['gap_pct']:.1f}%)")


if __name__ == "__main__":
    main()
