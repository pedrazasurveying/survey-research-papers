"""
Subagent 6B: FIGURE_BUILD — Paper 2
=====================================
Read Paper 2 analysis CSVs and produce publication-ready figures.

Usage:
    python scripts/s6b_figures_p2.py
    python scripts/s6b_figures_p2.py --indir analysis/p2 --outdir figures/p2
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# ---------------------------------------------------------------------------
# Style setup
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

# Colorblind-friendly palette
CB_BLUE = "#0072B2"
CB_ORANGE = "#E69F00"
CB_GREEN = "#009E73"
CB_RED = "#D55E00"
CB_PURPLE = "#CC79A7"
CB_GRAY = "#999999"


def load_csv(path):
    """Load CSV or return None."""
    if not path.exists():
        print(f"  WARNING: {path.name} not found. Skipping.")
        return None
    return pd.read_csv(path)


def save_fig(fig, outdir, name):
    """Save figure as PNG and PDF."""
    fig.savefig(outdir / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(outdir / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {name}.png / .pdf")


# ---------------------------------------------------------------------------
# Figure 1: Representation Ratios
# ---------------------------------------------------------------------------
def fig1_representation_ratios(ratios, outdir):
    """Horizontal bar chart of representation ratios with parity line."""
    print("\n[Figure 1] Representation Ratios...")

    # Filter to key categories
    key_cats = ["Female", "NH Black", "Hispanic", "NH Asian", "Veteran", "Male", "NH White"]
    plot_df = ratios[ratios["category"].isin(key_cats)].copy()

    if len(plot_df) == 0:
        print("  No data for representation ratios figure.")
        return

    plot_df = plot_df.sort_values("representation_ratio", ascending=True)

    # Color by ratio level
    colors = []
    for ratio in plot_df["representation_ratio"]:
        if pd.isna(ratio):
            colors.append(CB_GRAY)
        elif ratio < 0.5:
            colors.append(CB_RED)
        elif ratio < 0.8:
            colors.append(CB_ORANGE)
        elif ratio <= 1.2:
            colors.append(CB_GREEN)
        else:
            colors.append(CB_BLUE)

    fig, ax = plt.subplots(figsize=(7, 4.5))

    y_pos = range(len(plot_df))
    bars = ax.barh(y_pos, plot_df["representation_ratio"].fillna(0),
                   color=colors, edgecolor="white", height=0.6)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(plot_df["category"])
    ax.set_xlabel("Representation Ratio")

    # Parity line
    ax.axvline(x=1.0, color="black", linewidth=1.5, linestyle="--", alpha=0.7)
    ax.text(1.02, len(plot_df) - 0.5, "Parity", fontsize=9, va="bottom", alpha=0.7)

    # Underrepresentation threshold
    ax.axvline(x=0.5, color=CB_RED, linewidth=1, linestyle=":", alpha=0.5)

    # Value labels
    for i, (idx, row) in enumerate(plot_df.iterrows()):
        ratio = row["representation_ratio"]
        if not pd.isna(ratio):
            ax.text(ratio + 0.02, i, f"{ratio:.2f}", va="center", fontsize=9)

    ax.set_xlim(0, max(plot_df["representation_ratio"].max() * 1.15, 1.8))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    save_fig(fig, outdir, "fig1_representation_ratios")


# ---------------------------------------------------------------------------
# Figure 2: Wage Gaps
# ---------------------------------------------------------------------------
def fig2_wage_gaps(wage_gaps, outdir):
    """Grouped bar chart of median earnings by demographic group."""
    print("\n[Figure 2] Wage Gaps...")

    # Gender gap (surveyors only)
    gender = wage_gaps[
        (wage_gaps["comparison"].str.contains("Gender", na=False)) &
        (wage_gaps["occupation"] == "Surveyors") &
        (~wage_gaps["suppressed"])
    ]

    # Racial gaps (surveyors only)
    racial = wage_gaps[
        (wage_gaps["comparison"].str.contains("Race", na=False)) &
        (~wage_gaps["suppressed"])
    ]

    fig, axes = plt.subplots(1, 2, figsize=(10, 5), gridspec_kw={"width_ratios": [1, 1.5]})

    # Panel A: Gender
    ax = axes[0]
    if len(gender) > 0:
        g = gender.iloc[0]
        groups = ["Male", "Female"]
        values = [g["group_a_median"], g["group_b_median"]]
        colors_g = [CB_BLUE, CB_PURPLE]

        bars = ax.bar(groups, values, color=colors_g, width=0.5, edgecolor="white")

        # Dollar labels
        for bar, val in zip(bars, values):
            if not pd.isna(val):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1000,
                        f"${val:,.0f}", ha="center", va="bottom", fontsize=9)

        # Gap annotation
        gap_pct = g["gap_pct"]
        if not pd.isna(gap_pct):
            ax.annotate(
                f"Gap: {gap_pct:.1f}%",
                xy=(1, g["group_b_median"]),
                xytext=(1.3, (g["group_a_median"] + g["group_b_median"]) / 2),
                fontsize=9, color=CB_RED,
                arrowprops=dict(arrowstyle="->", color=CB_RED, lw=1.5),
            )

    ax.set_ylabel("Median Annual Earnings ($)")
    ax.set_title("(a) By Sex", fontsize=11)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Panel B: Race/Ethnicity
    ax = axes[1]
    if len(racial) > 0:
        # Add NH White reference
        race_labels = ["NH White"]
        race_values = [racial.iloc[0]["group_a_median"]]
        race_colors = [CB_BLUE]

        for _, r in racial.iterrows():
            race_labels.append(r["group_b"])
            race_values.append(r["group_b_median"])
            race_colors.append(CB_ORANGE)

        bars = ax.bar(range(len(race_labels)), race_values, color=race_colors,
                      width=0.5, edgecolor="white")
        ax.set_xticks(range(len(race_labels)))
        ax.set_xticklabels(race_labels, rotation=30, ha="right")

        for bar, val in zip(bars, race_values):
            if not pd.isna(val):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1000,
                        f"${val:,.0f}", ha="center", va="bottom", fontsize=9)

    ax.set_title("(b) By Race/Ethnicity", fontsize=11)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    fig.tight_layout()
    save_fig(fig, outdir, "fig2_wage_gaps")


# ---------------------------------------------------------------------------
# Figure 3: Intersectional Heatmap
# ---------------------------------------------------------------------------
def fig3_intersectional(intersectional, outdir):
    """Heatmap of weighted percent for race x sex."""
    print("\n[Figure 3] Intersectional Heatmap...")

    df = intersectional.copy()

    # Remove suppressed rows for the main visualization
    # but mark them
    df["display_pct"] = df["weighted_pct"].copy()
    df.loc[df["suppressed"] == True, "display_pct"] = np.nan

    # Pivot
    pivot = df.pivot_table(index="race_eth", columns="sex_r",
                           values="display_pct", aggfunc="first")

    if pivot.empty:
        print("  No intersectional data to plot.")
        return

    # Reorder rows by total share
    row_totals = pivot.sum(axis=1).sort_values(ascending=False)
    pivot = pivot.reindex(row_totals.index)

    # Ensure columns are in consistent order
    col_order = [c for c in ["Male", "Female"] if c in pivot.columns]
    pivot = pivot[col_order]

    fig, ax = plt.subplots(figsize=(6, 5))

    # Create annotation matrix
    annot = pivot.copy()
    for col in annot.columns:
        for idx in annot.index:
            val = annot.loc[idx, col]
            if pd.isna(val):
                annot.loc[idx, col] = "—"
            else:
                annot.loc[idx, col] = f"{val:.1f}%"

    sns.heatmap(pivot, annot=annot.values, fmt="", cmap="YlOrRd",
                linewidths=0.5, linecolor="white", ax=ax,
                cbar_kws={"label": "% of Surveyor Workforce"},
                vmin=0)

    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    fig.tight_layout()
    save_fig(fig, outdir, "fig3_intersectional")


# ---------------------------------------------------------------------------
# Figure 4: Metro vs Non-Metro
# ---------------------------------------------------------------------------
def fig4_metro_nonmetro(metro, outdir):
    """Side-by-side comparison of metro vs non-metro diversity."""
    print("\n[Figure 4] Metro vs Non-Metro...")

    if metro is None or len(metro) == 0:
        print("  No metro data to plot.")
        return

    metro_row = metro[metro["metro_status"] == "Metro"]
    nonmetro_row = metro[metro["metro_status"] == "Non-metro"]

    if len(metro_row) == 0 or len(nonmetro_row) == 0:
        print("  Incomplete metro/non-metro data.")
        return

    m = metro_row.iloc[0]
    nm = nonmetro_row.iloc[0]

    # Metrics to compare
    metrics = []
    labels = []

    for col, label in [("pct_nonwhite", "% Non-White"),
                        ("pct_female", "% Female")]:
        if col in m.index and col in nm.index:
            metrics.append(col)
            labels.append(label)

    if not metrics:
        print("  No comparable metrics found.")
        return

    fig, ax = plt.subplots(figsize=(7, 4.5))

    x = np.arange(len(labels))
    width = 0.3

    metro_vals = [m[col] for col in metrics]
    nonmetro_vals = [nm[col] for col in metrics]

    bars1 = ax.bar(x - width / 2, metro_vals, width, label="Metro",
                   color=CB_BLUE, edgecolor="white")
    bars2 = ax.bar(x + width / 2, nonmetro_vals, width, label="Non-Metro",
                   color=CB_ORANGE, edgecolor="white")

    # Value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if not pd.isna(height) and height > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, height + 0.5,
                        f"{height:.1f}%", ha="center", va="bottom", fontsize=10)

    # Gap annotations
    for i, (mv, nmv) in enumerate(zip(metro_vals, nonmetro_vals)):
        if not pd.isna(mv) and not pd.isna(nmv):
            gap = mv - nmv
            mid_y = max(mv, nmv) + 3
            ax.text(x[i], mid_y, f"Gap: {gap:.1f} pp",
                    ha="center", fontsize=9, color=CB_RED, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Percentage (%)")
    ax.legend(loc="upper right", frameon=False)

    ax.set_ylim(0, max(metro_vals + nonmetro_vals) * 1.3)

    fig.tight_layout()
    save_fig(fig, outdir, "fig4_metro_nonmetro")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Subagent 6B: FIGURE_BUILD — Paper 2")
    parser.add_argument("--indir", default="analysis/p2",
                        help="Input directory with analysis CSVs")
    parser.add_argument("--outdir", default="figures/p2",
                        help="Output directory for figures")
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not indir.exists():
        print(f"ERROR: Input directory not found: {indir}")
        print("Run s4b, s4c, s4d analysis scripts first.")
        sys.exit(1)

    print(f"Loading Paper 2 analysis from: {indir}")
    print(f"Saving figures to: {outdir}")

    # Load data
    ratios = load_csv(indir / "p2_representation_ratios.csv")
    wage_gaps = load_csv(indir / "p2_wage_gaps.csv")
    intersectional = load_csv(indir / "p2_intersectional.csv")
    metro = load_csv(indir / "p2_metro_nonmetro.csv")

    figs_built = 0

    if ratios is not None:
        fig1_representation_ratios(ratios, outdir)
        figs_built += 1

    if wage_gaps is not None:
        fig2_wage_gaps(wage_gaps, outdir)
        figs_built += 1

    if intersectional is not None:
        fig3_intersectional(intersectional, outdir)
        figs_built += 1

    if metro is not None:
        fig4_metro_nonmetro(metro, outdir)
        figs_built += 1

    print(f"\nDone. {figs_built} figures saved to {outdir}/")


if __name__ == "__main__":
    main()
