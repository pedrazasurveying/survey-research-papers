"""
Subagent 4D: GEOGRAPHIC_ANALYSIS
==================================
State-level demographic variation in the surveying workforce for Paper 2
(Demographic Disparity and Earnings Gaps in the U.S. Land Surveying Workforce).

Computes state-level composition, identifies outlier states, provides
metro/non-metro breakdown, and produces a Texas detailed analysis for
trade publication use.

Usage:
    python scripts/s4d_geographic_analysis.py
    python scripts/s4d_geographic_analysis.py --input data/surveying_recoded.csv --outdir analysis/p2
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_STATE_N = 30  # Minimum unweighted n per state for reporting

# STATEFIP to state name mapping (all 50 states + DC)
STATEFIP_NAMES = {
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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
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
    return float(v_sorted[min(idx, len(v_sorted) - 1)])


def compute_state_composition(state_df, state_name, statefip):
    """Compute demographic composition for a single state."""
    n = len(state_df)
    wt_total = state_df["PERWT"].sum()

    if n < MIN_STATE_N:
        return None  # Will be suppressed

    row = {
        "statefip": statefip,
        "state_name": state_name,
        "unweighted_n": n,
        "weighted_n": round(wt_total, 0),
    }

    # Sex distribution
    for sex in ["Male", "Female"]:
        mask = state_df["sex_r"] == sex
        row[f"pct_{sex.lower()}"] = round(
            state_df.loc[mask, "PERWT"].sum() / wt_total * 100, 2
        ) if wt_total > 0 else np.nan

    # Race/ethnicity distribution
    for race in ["NH White", "NH Black", "Hispanic", "NH Asian", "NH Other"]:
        mask = state_df["race_eth"] == race
        pct = state_df.loc[mask, "PERWT"].sum() / wt_total * 100 if wt_total > 0 else 0
        row[f"pct_{race.replace(' ', '_').replace('/', '_')}"] = round(pct, 2)

    # Non-white share
    nonwhite_mask = state_df["race_eth"] != "NH White"
    row["pct_nonwhite"] = round(
        state_df.loc[nonwhite_mask, "PERWT"].sum() / wt_total * 100, 2
    ) if wt_total > 0 else np.nan

    # Education distribution
    for educ in ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]:
        mask = state_df["educ_r"] == educ
        row[f"pct_educ_{educ.replace(' ', '_').replace('/', '_')}"] = round(
            state_df.loc[mask, "PERWT"].sum() / wt_total * 100, 2
        ) if wt_total > 0 else np.nan

    # Median age
    ages = state_df["AGE"].values
    weights = state_df["PERWT"].values
    valid = ~np.isnan(ages) & ~np.isnan(weights) & (weights > 0)
    if valid.sum() > 0:
        sorted_idx = np.argsort(ages[valid])
        cumwt = np.cumsum(weights[valid][sorted_idx])
        row["median_age"] = ages[valid][sorted_idx][
            np.searchsorted(cumwt, cumwt[-1] / 2)
        ]
    else:
        row["median_age"] = np.nan

    # Pct 55+
    row["pct_55plus"] = round(
        state_df.loc[state_df["AGE"] >= 55, "PERWT"].sum() / wt_total * 100, 2
    ) if wt_total > 0 else np.nan

    # Pct veteran (among those with valid status)
    vet_valid = state_df[state_df["veteran"].isin(["Veteran", "Non-veteran"])]
    if len(vet_valid) > 0:
        vet_wt = vet_valid["PERWT"].sum()
        row["pct_veteran"] = round(
            vet_valid.loc[vet_valid["veteran"] == "Veteran", "PERWT"].sum() / vet_wt * 100, 2
        ) if vet_wt > 0 else np.nan
    else:
        row["pct_veteran"] = np.nan

    # Median wage
    row["median_wage_adj"] = round(weighted_median(state_df["wage_adj"], state_df["PERWT"]), 0)

    # Self-employment rate
    row["pct_self_employed"] = round(
        state_df.loc[state_df["classwkr_r"] == "Self-employed", "PERWT"].sum() / wt_total * 100, 2
    ) if wt_total > 0 else np.nan

    return row


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------
def analyze_state_composition(df):
    """State-level demographic composition for OCC=1310."""
    print("\n[1/3] Computing state-level composition (OCC=1310)...")

    surveyors = df[df["OCC"] == 1310].copy()

    if "STATEFIP" not in surveyors.columns:
        print("  ERROR: STATEFIP not found in data. Cannot do state analysis.")
        return pd.DataFrame()

    # Compute national non-white share for comparison
    total_wt = surveyors["PERWT"].sum()
    national_nonwhite_pct = (
        surveyors.loc[surveyors["race_eth"] != "NH White", "PERWT"].sum() / total_wt * 100
    )
    print(f"  National non-white share (Surveyors): {national_nonwhite_pct:.1f}%")

    rows = []
    suppressed_states = []

    for fip, name in sorted(STATEFIP_NAMES.items(), key=lambda x: x[1]):
        state_df = surveyors[surveyors["STATEFIP"] == fip]
        if len(state_df) == 0:
            continue

        result = compute_state_composition(state_df, name, fip)
        if result is None:
            suppressed_states.append(f"{name} (n={len(state_df)})")
            continue

        # Flag states where minority share exceeds national average
        if result["pct_nonwhite"] > national_nonwhite_pct:
            result["positive_outlier"] = True
        else:
            result["positive_outlier"] = False

        rows.append(result)

    state_comp = pd.DataFrame(rows)

    if len(suppressed_states) > 0:
        print(f"  Suppressed {len(suppressed_states)} states with n < {MIN_STATE_N}:")
        for s in suppressed_states[:10]:
            print(f"    {s}")
        if len(suppressed_states) > 10:
            print(f"    ... and {len(suppressed_states) - 10} more")

    # Report positive outliers
    outliers = state_comp[state_comp["positive_outlier"] == True]
    if len(outliers) > 0:
        print(f"\n  States with minority share > national avg ({national_nonwhite_pct:.1f}%):")
        for _, row in outliers.sort_values("pct_nonwhite", ascending=False).head(10).iterrows():
            print(f"    {row['state_name']}: {row['pct_nonwhite']:.1f}% non-white (n={row['unweighted_n']})")

    # Report top states by workforce size
    print(f"\n  Top 10 states by surveyor workforce size:")
    for _, row in state_comp.nlargest(10, "weighted_n").iterrows():
        print(f"    {row['state_name']}: N={row['weighted_n']:,.0f} (n={row['unweighted_n']})")

    return state_comp


def analyze_texas_detail(df):
    """Detailed Texas breakdown for trade publications."""
    print("\n[2/3] Computing Texas detailed breakdown...")

    surveyors = df[df["OCC"] == 1310].copy()

    if "STATEFIP" not in surveyors.columns:
        print("  ERROR: STATEFIP not found in data.")
        return pd.DataFrame()

    texas = surveyors[surveyors["STATEFIP"] == 48]
    n_texas = len(texas)
    print(f"  Texas surveyors: n={n_texas}")

    if n_texas < MIN_STATE_N:
        print(f"  WARNING: Texas n={n_texas} < {MIN_STATE_N}. Suppressing detailed breakdown.")
        return pd.DataFrame()

    wt_total = texas["PERWT"].sum()
    rows = []

    # Race/ethnicity breakdown
    print("  Race/ethnicity:")
    for race in sorted(texas["race_eth"].unique()):
        mask = texas["race_eth"] == race
        n = mask.sum()
        wt = texas.loc[mask, "PERWT"].sum()
        pct = wt / wt_total * 100

        race_row = {
            "variable": "race_eth",
            "category": race,
            "weighted_pct": round(pct, 2),
            "weighted_n": round(wt, 0),
            "unweighted_n": n,
        }

        # Median wage for this race group if n >= MIN_STATE_N
        if n >= MIN_STATE_N:
            med_wage = weighted_median(texas.loc[mask, "wage_adj"], texas.loc[mask, "PERWT"])
            race_row["median_wage_adj"] = round(med_wage, 0) if not np.isnan(med_wage) else np.nan
        else:
            race_row["median_wage_adj"] = np.nan

        rows.append(race_row)
        print(f"    {race}: {pct:.1f}% (n={n}), "
              f"median wage=${race_row['median_wage_adj']:,.0f}" if not pd.isna(race_row["median_wage_adj"])
              else f"    {race}: {pct:.1f}% (n={n}), wage suppressed")

    # Education breakdown
    print("  Education:")
    for educ in ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]:
        mask = texas["educ_r"] == educ
        n = mask.sum()
        wt = texas.loc[mask, "PERWT"].sum()
        pct = wt / wt_total * 100

        educ_row = {
            "variable": "educ_r",
            "category": educ,
            "weighted_pct": round(pct, 2),
            "weighted_n": round(wt, 0),
            "unweighted_n": n,
        }

        if n >= MIN_STATE_N:
            med_wage = weighted_median(texas.loc[mask, "wage_adj"], texas.loc[mask, "PERWT"])
            educ_row["median_wage_adj"] = round(med_wage, 0) if not np.isnan(med_wage) else np.nan
        else:
            educ_row["median_wage_adj"] = np.nan

        rows.append(educ_row)
        print(f"    {educ}: {pct:.1f}% (n={n})")

    # Sex breakdown
    print("  Sex:")
    for sex in ["Male", "Female"]:
        mask = texas["sex_r"] == sex
        n = mask.sum()
        wt = texas.loc[mask, "PERWT"].sum()
        pct = wt / wt_total * 100

        sex_row = {
            "variable": "sex_r",
            "category": sex,
            "weighted_pct": round(pct, 2),
            "weighted_n": round(wt, 0),
            "unweighted_n": n,
        }

        if n >= MIN_STATE_N:
            med_wage = weighted_median(texas.loc[mask, "wage_adj"], texas.loc[mask, "PERWT"])
            sex_row["median_wage_adj"] = round(med_wage, 0) if not np.isnan(med_wage) else np.nan
        else:
            sex_row["median_wage_adj"] = np.nan

        rows.append(sex_row)
        print(f"    {sex}: {pct:.1f}% (n={n})")

    # Overall Texas summary
    med_wage_all = weighted_median(texas["wage_adj"], texas["PERWT"])
    rows.append({
        "variable": "OVERALL",
        "category": "All Texas Surveyors",
        "weighted_pct": 100.0,
        "weighted_n": round(wt_total, 0),
        "unweighted_n": n_texas,
        "median_wage_adj": round(med_wage_all, 0) if not np.isnan(med_wage_all) else np.nan,
    })
    print(f"  Overall Texas median wage: ${med_wage_all:,.0f}" if not np.isnan(med_wage_all) else "  Overall Texas median wage: N/A")

    return pd.DataFrame(rows)


def analyze_metro_nonmetro(df):
    """Metro vs non-metro demographic breakdown for OCC=1310."""
    print("\n[3/3] Computing metro vs non-metro breakdown...")

    surveyors = df[df["OCC"] == 1310].copy()

    if "METRO" not in surveyors.columns:
        print("  ERROR: METRO not found in data. Cannot do metro analysis.")
        return pd.DataFrame()

    # IPUMS METRO codes:
    # 0 = Not identifiable / mixed
    # 1 = Not in metro area
    # 2 = In metro area, central/principal city
    # 3 = In metro area, outside central/principal city
    # 4 = In metro area, central/principal city status unknown
    metro_map = {
        0: "Not identifiable",
        1: "Non-metro",
        2: "Metro (central city)",
        3: "Metro (suburban)",
        4: "Metro (city status unknown)",
    }

    # Simplified: metro vs non-metro
    surveyors["metro_r"] = surveyors["METRO"].map({
        0: "Not identifiable",
        1: "Non-metro",
        2: "Metro",
        3: "Metro",
        4: "Metro",
    })

    rows = []
    for metro_cat in ["Metro", "Non-metro", "Not identifiable"]:
        sub = surveyors[surveyors["metro_r"] == metro_cat]
        n = len(sub)

        if n < MIN_STATE_N:
            print(f"  {metro_cat}: n={n} < {MIN_STATE_N}, suppressing")
            continue

        wt_total = sub["PERWT"].sum()

        row = {
            "metro_status": metro_cat,
            "unweighted_n": n,
            "weighted_n": round(wt_total, 0),
        }

        # Sex
        for sex in ["Male", "Female"]:
            mask = sub["sex_r"] == sex
            row[f"pct_{sex.lower()}"] = round(
                sub.loc[mask, "PERWT"].sum() / wt_total * 100, 2
            ) if wt_total > 0 else np.nan

        # Race/ethnicity
        for race in ["NH White", "NH Black", "Hispanic", "NH Asian", "NH Other"]:
            mask = sub["race_eth"] == race
            row[f"pct_{race.replace(' ', '_').replace('/', '_')}"] = round(
                sub.loc[mask, "PERWT"].sum() / wt_total * 100, 2
            ) if wt_total > 0 else np.nan

        # Non-white share
        nonwhite_mask = sub["race_eth"] != "NH White"
        row["pct_nonwhite"] = round(
            sub.loc[nonwhite_mask, "PERWT"].sum() / wt_total * 100, 2
        ) if wt_total > 0 else np.nan

        # Education
        for educ in ["HS or less", "Some college or AA", "BA or BS", "Graduate degree"]:
            mask = sub["educ_r"] == educ
            row[f"pct_educ_{educ.replace(' ', '_').replace('/', '_')}"] = round(
                sub.loc[mask, "PERWT"].sum() / wt_total * 100, 2
            ) if wt_total > 0 else np.nan

        # Median wage
        row["median_wage_adj"] = round(weighted_median(sub["wage_adj"], sub["PERWT"]), 0)

        # Median age
        row["median_age"] = round(weighted_median(sub["AGE"].astype(float), sub["PERWT"]), 0)

        # Pct 55+
        row["pct_55plus"] = round(
            sub.loc[sub["AGE"] >= 55, "PERWT"].sum() / wt_total * 100, 2
        ) if wt_total > 0 else np.nan

        rows.append(row)
        print(f"  {metro_cat}: N={wt_total:,.0f}, {row['pct_nonwhite']:.1f}% non-white, "
              f"median wage=${row['median_wage_adj']:,.0f}")

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 4D: GEOGRAPHIC_ANALYSIS — state-level demographics for Paper 2"
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

    # Quick check for geographic variables
    has_statefip = "STATEFIP" in df.columns
    has_metro = "METRO" in df.columns
    print(f"  STATEFIP present: {has_statefip}")
    print(f"  METRO present: {has_metro}")

    if has_statefip:
        n_states = df[df["OCC"] == 1310]["STATEFIP"].nunique()
        print(f"  Surveyors in {n_states} states")

    print("\n" + "=" * 70)
    print("PAPER 2: GEOGRAPHIC ANALYSIS")
    print("=" * 70)

    # 1. State composition
    state_comp = analyze_state_composition(df)
    if len(state_comp) > 0:
        state_comp.to_csv(outdir / "p2_state_composition.csv", index=False)
        print(f"  -> Saved: {outdir}/p2_state_composition.csv ({len(state_comp)} states)")
    else:
        print("  -> No state composition data to save.")

    # 2. Texas detail
    texas_detail = analyze_texas_detail(df)
    if len(texas_detail) > 0:
        texas_detail.to_csv(outdir / "p2_texas_detail.csv", index=False)
        print(f"  -> Saved: {outdir}/p2_texas_detail.csv")
    else:
        print("  -> No Texas detail data to save.")

    # 3. Metro/non-metro
    metro = analyze_metro_nonmetro(df)
    if len(metro) > 0:
        metro.to_csv(outdir / "p2_metro_nonmetro.csv", index=False)
        print(f"  -> Saved: {outdir}/p2_metro_nonmetro.csv")
    else:
        print("  -> No metro/non-metro data to save.")

    print("\n" + "=" * 70)
    print("GEOGRAPHIC ANALYSIS COMPLETE")
    print(f"All outputs saved to: {outdir}/")
    print("=" * 70)

    # Key findings summary
    print("\nKEY FINDINGS SUMMARY:")

    if len(state_comp) > 0:
        # Most diverse states
        top_diverse = state_comp.nlargest(5, "pct_nonwhite")
        print("\n  Most diverse surveying workforces (by state):")
        for _, row in top_diverse.iterrows():
            print(f"    {row['state_name']}: {row['pct_nonwhite']:.1f}% non-white")

        # Highest wages
        top_wage = state_comp.nlargest(5, "median_wage_adj")
        print("\n  Highest median wages:")
        for _, row in top_wage.iterrows():
            print(f"    {row['state_name']}: ${row['median_wage_adj']:,.0f}")

        # States where positive outlier
        n_outliers = state_comp["positive_outlier"].sum()
        print(f"\n  States exceeding national minority share: {n_outliers}/{len(state_comp)}")

    if len(metro) > 0:
        print("\n  Metro vs non-metro diversity gap:")
        metro_row = metro[metro["metro_status"] == "Metro"]
        nonmetro_row = metro[metro["metro_status"] == "Non-metro"]
        if len(metro_row) > 0 and len(nonmetro_row) > 0:
            m_pct = metro_row.iloc[0]["pct_nonwhite"]
            nm_pct = nonmetro_row.iloc[0]["pct_nonwhite"]
            print(f"    Metro non-white: {m_pct:.1f}%")
            print(f"    Non-metro non-white: {nm_pct:.1f}%")
            print(f"    Gap: {m_pct - nm_pct:.1f} percentage points")


if __name__ == "__main__":
    main()
