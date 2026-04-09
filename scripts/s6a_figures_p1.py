"""
Subagent 6A: FIGURES_P1
========================
Read Paper 1 analysis CSV outputs (age distribution, retirement cliff,
geographic aging) and produce publication-ready figures for the workforce
aging and contraction paper.

Figures produced:
    1. fig1_median_age_comparison  -- Horizontal bar chart of median age
    2. fig2_replacement_pipeline   -- Grouped bar chart: % 55+ vs % 18-34
    3. fig3_state_aging            -- Top-20-states bar chart coloured by risk

Usage:
    python scripts/s6a_figures_p1.py
    python scripts/s6a_figures_p1.py --indir analysis/p1 --outdir figures/p1
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for CI / headless servers

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap

# ---------------------------------------------------------------------------
# APA-compatible style defaults
# ---------------------------------------------------------------------------
# Prefer a serif font; fall back gracefully if Times New Roman is absent.
_SERIF_FONTS = [
    "Times New Roman", "Times", "DejaVu Serif", "Bitstream Vera Serif",
    "Computer Modern Roman", "serif",
]

APA_RC = {
    "font.family": "serif",
    "font.serif": _SERIF_FONTS,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "lines.linewidth": 1.2,
    "patch.linewidth": 0.5,
    "pdf.fonttype": 42,       # TrueType embedding for PDF
    "ps.fonttype": 42,
}

# Colorblind-friendly palette (IBM Design / Wong)
CLR_SURVEYING_1 = "#0072B2"   # blue  -- Surveyors
CLR_SURVEYING_2 = "#009E73"   # teal  -- Survey technicians
CLR_BENCHMARK   = "#999999"   # gray  -- benchmark groups
CLR_55PLUS      = "#D55E00"   # vermilion -- age 55+
CLR_18_34       = "#56B4E9"   # sky blue  -- age 18-34
CLR_GAP         = "#CC79A7"   # reddish pink -- gap annotation

# Figure dimensions (inches) -- APA single-column friendly
FIG_W, FIG_H = 7, 5


# ---------------------------------------------------------------------------
# Ordered group list for Figures 1 & 2 (bottom-to-top for horizontal bars)
# ---------------------------------------------------------------------------
GROUP_ORDER = [
    "Construction trades",
    "Architecture & engineering",
    "All STEM",
    "U.S. workforce",
    "Survey technicians",
    "Surveyors",
]

# Map group name -> colour
GROUP_COLORS = {
    "Surveyors": CLR_SURVEYING_1,
    "Survey technicians": CLR_SURVEYING_2,
}


def _group_color(group_name: str) -> str:
    """Return bar colour for a given occupation group."""
    return GROUP_COLORS.get(group_name, CLR_BENCHMARK)


# ---------------------------------------------------------------------------
# Helper: save figure in both PNG and PDF
# ---------------------------------------------------------------------------
def _save_fig(fig, outdir: Path, stem: str):
    """Save *fig* as <outdir>/<stem>.png and .pdf."""
    for ext in ("png", "pdf"):
        path = outdir / f"{stem}.{ext}"
        fig.savefig(path, format=ext)
        print(f"  -> {path}")
    plt.close(fig)


def _coerce_bool_column(series: pd.Series) -> pd.Series:
    """Coerce a column that may contain bool, string 'True'/'False', or
    numeric 0/1 into a proper boolean Series."""
    if series.dtype == bool:
        return series
    if series.dtype == object:
        return series.astype(str).str.strip().str.lower().isin(
            {"true", "1", "yes"}
        )
    # Numeric: treat nonzero as True
    return series.fillna(0).astype(bool)


# ---------------------------------------------------------------------------
# Figure 1: Median Age by Occupation and Comparison Group
# ---------------------------------------------------------------------------
def figure1_median_age(age_df: pd.DataFrame, outdir: Path):
    """Horizontal bar chart of median age with 95 % CI error bars."""
    print("\nFigure 1: Median age comparison")

    # Keep only groups in the canonical order that exist in the data
    available = set(age_df["group"])
    ordered = [g for g in GROUP_ORDER if g in available]
    if not ordered:
        print("  WARNING: No matching groups found; skipping Figure 1.")
        return

    plot_df = age_df.set_index("group").loc[ordered].copy()

    # Compute symmetric CI half-widths for error bars.
    # Use explicit CI columns if present; otherwise fall back to 1.96 * SE.
    if "median_age_CI_lo" in plot_df.columns and "median_age_CI_hi" in plot_df.columns:
        plot_df["ci_half"] = np.where(
            plot_df["median_age_CI_hi"].notna() & plot_df["median_age_CI_lo"].notna(),
            (plot_df["median_age_CI_hi"] - plot_df["median_age_CI_lo"]) / 2.0,
            np.where(
                plot_df["median_age_SE"].notna(),
                1.96 * plot_df["median_age_SE"],
                0.0,
            ),
        )
    else:
        plot_df["ci_half"] = np.where(
            plot_df["median_age_SE"].notna(),
            1.96 * plot_df["median_age_SE"],
            0.0,
        )

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    y_pos = np.arange(len(ordered))
    colors = [_group_color(g) for g in ordered]

    ax.barh(
        y_pos,
        plot_df["median_age"].values,
        xerr=plot_df["ci_half"].values,
        color=colors,
        edgecolor="white",
        height=0.6,
        capsize=3,
        error_kw={"linewidth": 0.8, "capthick": 0.8},
        zorder=3,
    )

    # Reference line at U.S. workforce median age
    us_row = age_df[age_df["group"] == "U.S. workforce"]
    if len(us_row) == 1:
        ref_age = float(us_row["median_age"].iloc[0])
        ax.axvline(
            ref_age, color="#444444", linewidth=0.7, linestyle="--", zorder=2,
        )
        ax.text(
            ref_age + 0.3,
            len(ordered) - 0.15,
            f"U.S. workforce\nmedian = {ref_age:.1f}",
            fontsize=8,
            color="#444444",
            va="top",
        )

    # Value labels at end of each bar
    for i, (grp, row) in enumerate(plot_df.iterrows()):
        age_val = row["median_age"]
        ci = row["ci_half"]
        if pd.notna(row.get("median_age_SE")) and row["median_age_SE"] > 0:
            label = f" {age_val:.1f} (SE {row['median_age_SE']:.1f})"
        else:
            label = f" {age_val:.1f}"
        ax.text(age_val + ci + 0.3, i, label, va="center", fontsize=8.5)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ordered)
    ax.set_xlabel("Median Age (years)")

    # x-axis lower bound: round down a bit below the smallest bar
    min_age = plot_df["median_age"].min()
    ax.set_xlim(left=max(0, min_age - 5))

    # Ensure x-axis upper limit gives room for labels
    max_edge = (plot_df["median_age"] + plot_df["ci_half"]).max()
    ax.set_xlim(right=max_edge + 10)

    ax.invert_yaxis()  # top group first
    fig.tight_layout()
    _save_fig(fig, outdir, "fig1_median_age_comparison")


# ---------------------------------------------------------------------------
# Figure 2: Replacement Pipeline Gap (% 55+ vs % 18-34)
# ---------------------------------------------------------------------------
def figure2_pipeline_gap(age_df: pd.DataFrame, cliff_df: pd.DataFrame,
                         outdir: Path):
    """Grouped bar chart showing % 55+ and % 18-34 side by side."""
    print("\nFigure 2: Replacement pipeline gap")

    available = set(age_df["group"])
    ordered = [g for g in GROUP_ORDER if g in available]
    if not ordered:
        print("  WARNING: No matching groups found; skipping Figure 2.")
        return

    plot_df = age_df.set_index("group").loc[ordered].copy()

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    y_pos = np.arange(len(ordered))
    bar_h = 0.35

    bars_55 = ax.barh(
        y_pos - bar_h / 2,
        plot_df["pct_55plus"].values,
        height=bar_h,
        color=CLR_55PLUS,
        edgecolor="white",
        label="% Aged 55+",
        zorder=3,
    )
    bars_18 = ax.barh(
        y_pos + bar_h / 2,
        plot_df["pct_18_34"].values,
        height=bar_h,
        color=CLR_18_34,
        edgecolor="white",
        label="% Aged 18\u201334",
        zorder=3,
    )

    # Annotate each bar with its value
    for i, (grp, row) in enumerate(plot_df.iterrows()):
        v55 = row["pct_55plus"]
        v18 = row["pct_18_34"]
        if pd.notna(v55):
            ax.text(v55 + 0.5, i - bar_h / 2, f"{v55:.1f}%",
                    va="center", fontsize=8)
        if pd.notna(v18):
            ax.text(v18 + 0.5, i + bar_h / 2, f"{v18:.1f}%",
                    va="center", fontsize=8)

    # Annotate the gap for Surveyors with a prominent bracket
    if "Surveyors" in plot_df.index:
        sv = plot_df.loc["Surveyors"]
        gap = sv["pct_55plus"] - sv["pct_18_34"]
        sv_idx = ordered.index("Surveyors")

        # Try to get the gap SE from the cliff table
        gap_ci_text = ""
        if cliff_df is not None and len(cliff_df) > 0:
            gap_row = cliff_df[
                cliff_df["metric"].str.contains("cliff gap", case=False)
            ]
            if len(gap_row) == 1:
                se = gap_row["SE"].iloc[0]
                if pd.notna(se) and se > 0:
                    gap_ci_text = f" (SE = {se:.1f})"

        # Draw a bracket connecting the two bars
        mid_x = max(sv["pct_55plus"], sv["pct_18_34"]) + 4
        ax.annotate(
            "",
            xy=(mid_x, sv_idx - bar_h / 2),
            xytext=(mid_x, sv_idx + bar_h / 2),
            arrowprops=dict(
                arrowstyle="<->", color=CLR_GAP, lw=1.5,
                connectionstyle="arc3,rad=0",
            ),
        )
        sign = "+" if gap >= 0 else ""
        ax.text(
            mid_x + 1.0,
            sv_idx,
            f"Gap: {sign}{gap:.1f} pp{gap_ci_text}",
            va="center",
            fontsize=9,
            color=CLR_GAP,
            fontweight="bold",
        )

    # Also annotate gap for Survey technicians if present
    if "Survey technicians" in plot_df.index:
        st = plot_df.loc["Survey technicians"]
        gap_st = st["pct_55plus"] - st["pct_18_34"]
        st_idx = ordered.index("Survey technicians")
        mid_x_st = max(st["pct_55plus"], st["pct_18_34"]) + 4
        sign_st = "+" if gap_st >= 0 else ""
        ax.text(
            mid_x_st + 1.0,
            st_idx,
            f"Gap: {sign_st}{gap_st:.1f} pp",
            va="center",
            fontsize=8,
            color="#666666",
            fontstyle="italic",
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ordered)
    ax.set_xlabel("Share of Workers (%)")
    ax.set_xlim(left=0)

    # Provide room for annotations
    max_val = 0.0
    if plot_df["pct_55plus"].notna().any():
        max_val = max(max_val, plot_df["pct_55plus"].max())
    if plot_df["pct_18_34"].notna().any():
        max_val = max(max_val, plot_df["pct_18_34"].max())
    ax.set_xlim(right=max_val + 22)

    ax.invert_yaxis()
    ax.legend(loc="lower right", frameon=False)

    fig.tight_layout()
    _save_fig(fig, outdir, "fig2_replacement_pipeline")


# ---------------------------------------------------------------------------
# Figure 3: State-Level Aging (Top 20 by employment, coloured by risk)
# ---------------------------------------------------------------------------
def figure3_state_aging(geo_df: pd.DataFrame, outdir: Path):
    """Horizontal bar chart of top-20 states coloured by pct_55plus."""
    print("\nFigure 3: State-level aging")

    if len(geo_df) == 0:
        print("  WARNING: Geographic data is empty; skipping Figure 3.")
        return

    # Ensure high_risk_flag is boolean
    if "high_risk_flag" in geo_df.columns:
        geo_df = geo_df.copy()
        geo_df["high_risk_flag"] = _coerce_bool_column(geo_df["high_risk_flag"])

    # Sort by weighted employment and take top 20
    n_states = min(20, len(geo_df))
    top = geo_df.nlargest(n_states, "weighted_n").copy()
    top = top.sort_values("weighted_n", ascending=True)  # for horizontal bar

    # Adjust figure height if fewer than 20 states
    fig_h = max(4, FIG_H + 1) if n_states >= 15 else max(3.5, n_states * 0.35 + 1.5)
    fig, ax = plt.subplots(figsize=(FIG_W, fig_h))

    # Colour gradient: green (low risk) -> yellow -> red (high risk >= 40)
    risk_cmap = LinearSegmentedColormap.from_list(
        "risk",
        ["#2CA02C", "#FFC107", "#D62728"],  # green, amber, red
        N=256,
    )
    # Normalise pct_55plus to [10, 50] range for colour mapping
    vmin, vmax = 10, 50
    pct_values = top["pct_55plus"].fillna(0).values
    norm_vals = np.clip(pct_values, vmin, vmax)
    normed = (norm_vals - vmin) / (vmax - vmin)
    bar_colors = [risk_cmap(v) for v in normed]

    y_pos = np.arange(len(top))
    bars = ax.barh(
        y_pos,
        top["weighted_n"].values,
        color=bar_colors,
        edgecolor="white",
        height=0.7,
        zorder=3,
    )

    # Annotate median age and high-risk flag to the right of each bar
    max_wt = top["weighted_n"].max()
    for i, (_, row) in enumerate(top.iterrows()):
        # Build annotation text: median age + pct 55+
        age_text = f" {row['median_age']:.0f} yr"
        is_high_risk = (
            row.get("high_risk_flag", False)
            if "high_risk_flag" in row.index else False
        )
        if is_high_risk:
            age_text += "  *"  # asterisk marks high-risk states (55+ >= 40%)
        pct_text = f"({row['pct_55plus']:.0f}% aged 55+)"
        ax.text(
            row["weighted_n"] + max_wt * 0.01,
            i,
            f"{age_text}  {pct_text}",
            va="center",
            fontsize=8,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(top["state"].values)
    ax.set_xlabel("Estimated Workforce (weighted N)")

    # Format x-axis with comma separator
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{int(x):,}"
    ))

    ax.set_xlim(right=max_wt * 1.40)  # room for annotations

    # Colour bar legend for pct_55plus
    sm = plt.cm.ScalarMappable(
        cmap=risk_cmap,
        norm=plt.Normalize(vmin=vmin, vmax=vmax),
    )
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, shrink=0.6, aspect=25)
    cbar.set_label("% Aged 55+", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    # Footnote for high-risk marker
    has_any_high_risk = (
        "high_risk_flag" in top.columns and top["high_risk_flag"].any()
    )
    if has_any_high_risk:
        fig.text(
            0.01, -0.01,
            "* High-risk state (55+ share \u2265 40%)",
            fontsize=7.5, color="#666666", ha="left", va="top",
        )

    fig.tight_layout()
    _save_fig(fig, outdir, "fig3_state_aging")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 6A: Publication-ready figures for Paper 1 "
                    "(Workforce Aging and Contraction)"
    )
    parser.add_argument(
        "--indir", default="analysis/p1",
        help="Directory containing Paper 1 analysis CSVs (default: analysis/p1)",
    )
    parser.add_argument(
        "--outdir", default="figures/p1",
        help="Output directory for figures (default: figures/p1)",
    )
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)

    if not indir.exists():
        print(f"ERROR: Input directory does not exist: {indir}")
        print("Run s4a_aging_analysis.py first to generate Paper 1 CSVs.")
        sys.exit(1)

    outdir.mkdir(parents=True, exist_ok=True)

    # Apply APA-compatible style
    plt.rcParams.update(APA_RC)

    # ------------------------------------------------------------------
    # Load CSVs (handle missing files gracefully)
    # ------------------------------------------------------------------
    age_path = indir / "p1_age_distribution.csv"
    cliff_path = indir / "p1_retirement_cliff.csv"
    geo_path = indir / "p1_geographic_aging.csv"

    age_df = None
    cliff_df = None
    geo_df = None

    if age_path.exists():
        age_df = pd.read_csv(age_path)
        print(f"Loaded {age_path} ({len(age_df)} rows)")
    else:
        print(f"WARNING: {age_path} not found. Figures 1 and 2 will be skipped.")

    if cliff_path.exists():
        cliff_df = pd.read_csv(cliff_path)
        print(f"Loaded {cliff_path} ({len(cliff_df)} rows)")
    else:
        print(f"WARNING: {cliff_path} not found. Figure 2 gap annotation "
              f"will lack CI detail.")

    if geo_path.exists():
        geo_df = pd.read_csv(geo_path)
        print(f"Loaded {geo_path} ({len(geo_df)} rows)")
    else:
        print(f"WARNING: {geo_path} not found. Figure 3 will be skipped.")

    # ------------------------------------------------------------------
    # Generate figures
    # ------------------------------------------------------------------
    n_produced = 0

    if age_df is not None and len(age_df) > 0:
        figure1_median_age(age_df, outdir)
        n_produced += 1

        figure2_pipeline_gap(age_df, cliff_df, outdir)
        n_produced += 1

    if geo_df is not None and len(geo_df) > 0:
        figure3_state_aging(geo_df, outdir)
        n_produced += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("PAPER 1 FIGURES COMPLETE")
    print("=" * 65)
    print(f"  {n_produced} figure(s) produced in: {outdir}")
    if n_produced > 0:
        for f in sorted(outdir.glob("fig*")):
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name}  ({size_kb:.1f} KB)")
    else:
        print("  No figures were produced. Ensure analysis CSVs exist in "
              f"{indir}.")


if __name__ == "__main__":
    main()
