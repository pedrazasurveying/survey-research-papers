"""
Subagent 2: RECODE
===================
Construct all shared analysis variables from raw IPUMS codes.

Usage:
    python scripts/s2_recode.py --input data/surveying_filtered.csv --output data/surveying_recoded.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# CPI-U annual deflators to adjust to 2024 dollars
# Source: BLS CPI-U annual averages. Update if final 2024 value changes.
CPI_DEFLATORS = {
    2019: 1.188,
    2020: 1.172,
    2021: 1.113,
    2022: 1.047,
    2023: 1.031,
    2024: 1.000,
}

# IPUMS missing codes to convert to NaN
IPUMS_MISSING = [999998, 999999, 9999998, 9999999]


def recode_sex(df: pd.DataFrame) -> pd.Series:
    """SEX: 1=Male, 2=Female."""
    return df["SEX"].map({1: "Male", 2: "Female"})


def recode_race_ethnicity(df: pd.DataFrame) -> pd.Series:
    """
    Construct race_eth variable.
    Hispanic origin takes precedence over race.
    """
    conditions = [
        df["HISPAN"].between(1, 4),                          # Hispanic (any race)
        (df["HISPAN"] == 0) & (df["RACE"] == 1),             # NH White
        (df["HISPAN"] == 0) & (df["RACE"] == 2),             # NH Black
        (df["HISPAN"] == 0) & (df["RACE"].isin([4, 5, 6])),  # NH Asian
        (df["HISPAN"] == 0) & (df["RACE"] == 3),             # NH AIAN
        (df["HISPAN"] == 0),                                  # NH Other/Multiracial
    ]
    choices = [
        "Hispanic",
        "NH White",
        "NH Black",
        "NH Asian",
        "NH AIAN",
        "NH Other/Multiracial",
    ]
    return pd.Series(np.select(conditions, choices, default="Unknown"), index=df.index)


def recode_education(df: pd.DataFrame) -> pd.Series:
    """Education -> 4-category variable. Uses EDUCD if available, falls back to EDUC."""
    if "EDUCD" in df.columns:
        # EDUCD detailed codes
        edu = df["EDUCD"]
        conditions = [
            edu <= 61,                     # HS or less
            edu.between(62, 81),           # Some college or AA
            edu == 101,                    # BA or BS
            edu >= 114,                    # Graduate degree
        ]
    elif "EDUC" in df.columns:
        # EDUC general codes (fallback)
        # 0-6: HS or less, 7-9: Some college/AA, 10: BA/BS, 11: Graduate
        edu = df["EDUC"]
        conditions = [
            edu <= 6,                      # HS or less
            edu.between(7, 9),             # Some college or AA
            edu == 10,                     # 4 years of college (BA/BS)
            edu >= 11,                     # 5+ years (Graduate)
        ]
    else:
        print("  WARNING: Neither EDUCD nor EDUC found. Education recode skipped.")
        return pd.Series("Unknown", index=df.index)

    choices = [
        "HS or less",
        "Some college or AA",
        "BA or BS",
        "Graduate degree",
    ]
    return pd.Series(np.select(conditions, choices, default="Unknown"), index=df.index)


def recode_agegroup(df: pd.DataFrame) -> pd.Series:
    """Age -> 6-category age group."""
    bins = [17, 24, 34, 44, 54, 64, 120]
    labels = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    return pd.cut(df["AGE"], bins=bins, labels=labels, right=True)


def recode_veteran(df: pd.DataFrame) -> pd.Series:
    """VETSTAT: 1=Non-veteran, 2=Veteran, 0=N/A."""
    return df["VETSTAT"].map({2: "Veteran", 1: "Non-veteran", 0: "N/A"})


def recode_classwkr(df: pd.DataFrame) -> pd.Series:
    """CLASSWKR -> 3-category class of worker."""
    conditions = [
        df["CLASSWKR"] == 22,                     # Private wage/salary
        df["CLASSWKR"].isin([25, 27, 28]),         # Government
        df["CLASSWKR"].isin([10, 13, 14]),         # Self-employed
    ]
    choices = [
        "Private wage/salary",
        "Government",
        "Self-employed",
    ]
    return pd.Series(np.select(conditions, choices, default="Other/Unknown"), index=df.index)


def recode_occ_label(df: pd.DataFrame) -> pd.Series:
    """OCC code -> readable label."""
    return df["OCC"].map({
        1520: "Cartographers",
        1530: "Surveyors",
        1560: "Technicians",
    })


def compute_wage_adj(df: pd.DataFrame) -> pd.Series:
    """Adjust INCEARN to 2023 dollars using CPI-U deflators."""
    wage = df["INCEARN"].copy().astype(float)

    # Set IPUMS missing codes to NaN
    wage[wage.isin(IPUMS_MISSING)] = np.nan

    # Set zero earnings for employed persons to NaN (likely non-response)
    if "EMPSTAT" in df.columns:
        employed_zero = (df["EMPSTAT"] == 1) & (wage == 0)
        wage[employed_zero] = np.nan

    # Apply CPI deflators by year
    for year, deflator in CPI_DEFLATORS.items():
        mask = df["YEAR"] == year
        wage[mask] = wage[mask] * deflator

    return wage


def compute_hourly_wage(df: pd.DataFrame, wage_adj: pd.Series) -> pd.Series:
    """Compute hourly wage from annual earnings and hours."""
    hours = df["UHRSWORK"].copy().astype(float)
    hours[hours == 0] = np.nan
    hourly = wage_adj / (hours * 52)
    # Cap extreme values (likely data errors)
    hourly[hourly > 500] = np.nan
    hourly[hourly < 1] = np.nan
    return hourly


def check_small_groups(df: pd.DataFrame, var: str, occ_code: int):
    """Check for small cell sizes and suggest combining categories."""
    subset = df[df["OCC"] == occ_code]
    counts = subset.groupby(var).size()
    small = counts[counts < 100]
    if len(small) > 0:
        print(f"  WARNING: Small unweighted cells in {var} for OCC={occ_code}:")
        for cat, n in small.items():
            print(f"    {cat}: n={n}")
        print(f"    Consider combining or suppressing in tables.")


def main():
    parser = argparse.ArgumentParser(description="Subagent 2: RECODE")
    parser.add_argument("--input", default="data/surveying_filtered.csv",
                        help="Path to filtered data from S1")
    parser.add_argument("--output", default="data/surveying_recoded.csv",
                        help="Output path for recoded data")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("Run s1_data_ingest.py first.")
        sys.exit(1)

    print(f"Loading: {input_path}")
    df = pd.read_csv(input_path)
    print(f"  {len(df):,} rows loaded.")

    # Clean IPUMS missing codes in key variables
    for var in ["INCEARN", "INCWAGE", "EDUCD", "VETSTAT"]:
        if var in df.columns:
            n_missing = df[var].isin(IPUMS_MISSING).sum()
            if n_missing > 0:
                print(f"  Cleaning {n_missing} IPUMS missing codes in {var}")
                df.loc[df[var].isin(IPUMS_MISSING), var] = np.nan

    # Apply recodes
    print("\nApplying recodes...")

    df["sex_r"] = recode_sex(df)
    print(f"  sex_r: {df['sex_r'].value_counts().to_dict()}")

    df["race_eth"] = recode_race_ethnicity(df)
    print(f"  race_eth: {df['race_eth'].value_counts().to_dict()}")

    df["educ_r"] = recode_education(df)
    print(f"  educ_r: {df['educ_r'].value_counts().to_dict()}")

    df["agegroup"] = recode_agegroup(df)
    print(f"  agegroup: {df['agegroup'].value_counts().sort_index().to_dict()}")

    df["age_55plus"] = (df["AGE"] >= 55).astype(int)
    print(f"  age_55plus: {df['age_55plus'].value_counts().to_dict()}")

    df["veteran"] = recode_veteran(df)
    print(f"  veteran: {df['veteran'].value_counts().to_dict()}")

    df["classwkr_r"] = recode_classwkr(df)
    print(f"  classwkr_r: {df['classwkr_r'].value_counts().to_dict()}")

    df["occ_label"] = recode_occ_label(df)
    print(f"  occ_label: {df['occ_label'].value_counts().to_dict()}")

    df["fulltime"] = (df["UHRSWORK"] >= 35).astype(int)
    print(f"  fulltime: {df['fulltime'].value_counts().to_dict()}")

    df["wage_adj"] = compute_wage_adj(df)
    valid_wages = df["wage_adj"].notna().sum()
    print(f"  wage_adj: {valid_wages:,} valid values, "
          f"median=${df['wage_adj'].median():,.0f}")

    df["hourly_wage"] = compute_hourly_wage(df, df["wage_adj"])
    valid_hourly = df["hourly_wage"].notna().sum()
    print(f"  hourly_wage: {valid_hourly:,} valid values, "
          f"median=${df['hourly_wage'].median():,.2f}/hr")

    # Check for small groups that may need combining
    print("\nChecking cell sizes...")
    for occ_code in [1530, 1560]:
        check_small_groups(df, "race_eth", occ_code)
        check_small_groups(df, "veteran", occ_code)

    # Check if NH AIAN and NH Other need combining
    for occ_code in [1530, 1560]:
        subset = df[df["OCC"] == occ_code]
        aian_n = (subset["race_eth"] == "NH AIAN").sum()
        other_n = (subset["race_eth"] == "NH Other/Multiracial").sum()
        if aian_n < 100 and other_n < 100:
            print(f"\n  NOTE (OCC={occ_code}): NH AIAN (n={aian_n}) and "
                  f"NH Other/Multiracial (n={other_n}) both < 100.")
            print(f"    Per CLAUDE.md: combine into 'NH Other' for tables.")
            # Create combined version
            mask = (df["OCC"] == occ_code) & df["race_eth"].isin(
                ["NH AIAN", "NH Other/Multiracial"])
            df.loc[mask, "race_eth"] = "NH Other"

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving recoded data to: {output_path}")
    df.to_csv(output_path, index=False)
    print(f"Done. {len(df):,} rows, {len(df.columns)} columns saved.")


if __name__ == "__main__":
    main()
