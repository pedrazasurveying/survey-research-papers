"""
Subagent 6B: FIGURES_P2
========================
Read Paper 2 analysis CSV outputs (demographic composition, representation
ratios, intersectional cross-tabs, wage gaps, metro/non-metro) and produce
publication-ready figures for the demographic disparity and earnings gaps paper.

Figures produced:
    1. fig1_representation_ratios   -- Horizontal bar: surveyor vs U.S. workforce
    2. fig2_wage_gaps               -- Grouped bar: gender and racial earnings
    3. fig3_intersectional_heatmap  -- Heatmap: race x sex weighted share
    4. fig4_metro_nonmetro          -- Grouped bar: metro vs non-metro diversity

Usage:
    python scripts/s6b_figures_p2.py
    python scripts/s6b_figures_p2.py --indir analysis/p2 --outdir figures/p2
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
from matplotlib.patches import Patch

# ---------------------------------------------------------------------------
# APA-compatible style defaults
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Colorblind-friendly palette (IBM Design / Wong)
# ---------------------------------------------------------------------------
CLR_SEVERE_UNDER = "#D55E00"   # vermilion -- severe underrep (<0.5)
CLR_UNDER        = "#E69F00"   # orange    -- underrep (0.5-0.8)
CLR_PARITY       = "#009E73"   # teal      -- near-parity (0.8-1.2)
CLR_OVER         = "#0072B2"   # blue      -- overrep (>1.2)

CLR_MALE         = "#0072B2"   # blue
CLR_FEMALE       = "#CC79A7"   # reddish pink

CLR_NH_WHITE     = "#0072B2"   # blue
CLR_HISPANIC     = "#E69F00"   # orange
CLR_NH_BLACK     = "#D55E00"   # vermilion
CLR_NH_ASIAN     = "#56B4E9"   # sky blue
CLR_NH_OTHER     = "#999999"   # gray

CLR_METRO        = "#0072B2"   # blue
CLR_NONMETRO     = "#E69F00"   # orange

CLR_GAP_ANNOT    = "#444444"   # dark gray for annotations

# Figure dimensions (inches) -- APA single-column friendly
FIG_W, FIG_H = 7, 5


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


def _fmt_dollars(val):
    """Format a dollar value as $XX,XXX."""
    if pd.isna(val):
        return ""
    return f"${val:,.0f}"


# ---------------------------------------------------------------------------
# Figure 1: Representation Ratios -- Surveyors vs. U.S. Workforce
# ---------------------------------------------------------------------------
# Canonical display order (bottom-to-top when y-axis is inverted).
# Tuple: (variable column value, category column value, display label)
RATIO_DISPLAY = [
    ("sex_r",    "Female",   "Female"),
    ("race_eth", "NH Black", "NH Black"),
    ("race_eth", "Hispanic", "Hispanic"),
    ("race_eth", "NH Asian", "NH Asian"),
    ("veteran",  "Veteran",  "Veteran"),
]


def _ratio_color(ratio: float) -> str:
    """Return bar colour based on representation ratio band."""
    if pd.isna(ratio):
        return "#CCCCCC"
    if ratio < 0.5:
        return CLR_SEVERE_UNDER
    if ratio < 0.8:
        return CLR_UNDER
    if ratio <= 1.2:
        return CLR_PARITY
    return CLR_OVER


def figure1_representation_ratios(ratio_df: pd.DataFrame, outdir: Path):
    """Horizontal bar chart of representation ratios with parity line."""
    print("\nFigure 1: Representation ratios")

    ratio_df = ratio_df.copy()

    # Build a keyed lookup
    ratio_df["_key"] = list(zip(ratio_df["variable"], ratio_df["category"]))

    labels = []
    ratios = []
    colors = []
    for var, cat, display_label in RATIO_DISPLAY:
        match = ratio_df[ratio_df["_key"] == (var, cat)]
        if len(match) == 0:
            continue
        row = match.iloc[0]
        r = row["representation_ratio"]
        if pd.isna(r):
            continue
        labels.append(display_label)
        ratios.append(r)
        colors.append(_ratio_color(r))

    if not labels:
        print("  WARNING: No matching groups found; skipping Figure 1.")
        return

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    y_pos = np.arange(len(labels))
    ax.barh(
        y_pos,
        ratios,
        color=colors,
        edgecolor="white",
        height=0.55,
        zorder=3,
    )

    # Parity reference line at 1.0
    ax.axvline(1.0, color="#333333", linewidth=0.9, linestyle="--", zorder=2)
    ax.text(
        1.02, len(labels) - 0.15, "Parity",
        fontsize=8, color="#333333", va="top", fontstyle="italic",
    )

    # Severe underrepresentation threshold at 0.5
    ax.axvline(0.5, color=CLR_SEVERE_UNDER, linewidth=0.7, linestyle=":",
               zorder=2, alpha=0.5)

    # Value labels to the right of each bar
    for i, r in enumerate(ratios):
        ax.text(
            r + 0.03, i, f"{r:.2f}",
            va="center", ha="left", fontsize=9, fontweight="bold",
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Representation Ratio (Surveyor Share \u00f7 U.S. Workforce Share)")
    ax.set_xlim(left=0, right=max(ratios) + 0.35)
    ax.invert_yaxis()  # first item at top

    # Legend for color bands
    legend_elements = [
        Patch(facecolor=CLR_SEVERE_UNDER, edgecolor="white",
              label="Severe under-rep. (< 0.50)"),
        Patch(facecolor=CLR_UNDER, edgecolor="white",
              label="Under-rep. (0.50\u20130.80)"),
        Patch(facecolor=CLR_PARITY, edgecolor="white",
              label="Near parity (0.80\u20131.20)"),
        Patch(facecolor=CLR_OVER, edgecolor="white",
              label="Over-rep. (> 1.20)"),
    ]
    ax.legend(
        handles=legend_elements, loc="lower right", frameon=True,
        framealpha=0.9, fontsize=8, edgecolor="#CCCCCC",
    )

    fig.tight_layout()
    _save_fig(fig, outdir, "fig1_representation_ratios")


# ---------------------------------------------------------------------------
# Figure 2: Gender and Racial Wage Gaps (two-panel)
# ---------------------------------------------------------------------------
RACE_CLR_MAP = {
    "NH White": CLR_NH_WHITE,
    "Hispanic": CLR_HISPANIC,
    "NH Black": CLR_NH_BLACK,
    "NH Asian": CLR_NH_ASIAN,
    "NH Other": CLR_NH_OTHER,
}


def figure2_wage_gaps(gaps_df: pd.DataFrame, outdir: Path):
    """Two-panel figure: (a) gender gap and (b) racial gaps, Surveyors only."""
    print("\nFigure 2: Gender and racial wage gaps")

    gaps_df = gaps_df.copy()

    # ---- Filter to unsuppressed Surveyor rows ----
    gender_rows = gaps_df[
        (gaps_df["occupation"] == "Surveyors")
        & (gaps_df["comparison"].str.contains("Gender", case=False))
        & (~gaps_df["suppressed"])
    ]
    race_rows = gaps_df[
        (gaps_df["occupation"] == "Surveyors")
        & (gaps_df["comparison"].str.contains("Race", case=False))
        & (~gaps_df["suppressed"])
    ]

    has_gender = len(gender_rows) > 0
    has_race = len(race_rows) > 0

    if not has_gender and not has_race:
        print("  WARNING: No unsuppressed wage gap data; skipping Figure 2.")
        return

    # Decide layout: two panels if both, one panel otherwise
    n_panels = int(has_gender) + int(has_race)
    if n_panels == 2:
        width_ratios = [1, max(1, len(race_rows) + 1) / 2]
        fig, axes = plt.subplots(
            1, 2, figsize=(FIG_W + 2, FIG_H),
            gridspec_kw={"width_ratios": width_ratios},
        )
        ax_gender = axes[0] if has_gender else None
        ax_race = axes[1] if has_race else None
    else:
        fig, ax_single = plt.subplots(figsize=(FIG_W, FIG_H))
        ax_gender = ax_single if has_gender else None
        ax_race = ax_single if has_race else None

    # ---- Panel A: Gender wage gap ----
    if has_gender and ax_gender is not None:
        gr = gender_rows.iloc[0]
        labels_g = [gr["group_a"], gr["group_b"]]
        vals_g = [gr["group_a_median"], gr["group_b_median"]]
        errs_g = [
            1.96 * gr["group_a_se"] if pd.notna(gr["group_a_se"]) else 0,
            1.96 * gr["group_b_se"] if pd.notna(gr["group_b_se"]) else 0,
        ]
        colors_g = [CLR_MALE, CLR_FEMALE]

        bars = ax_gender.bar(
            labels_g, vals_g, yerr=errs_g, color=colors_g,
            width=0.5, edgecolor="white", capsize=4,
            error_kw={"linewidth": 0.8, "capthick": 0.8}, zorder=3,
        )

        # Dollar labels above bars
        for bar_obj, val, err in zip(bars, vals_g, errs_g):
            if pd.notna(val):
                ax_gender.text(
                    bar_obj.get_x() + bar_obj.get_width() / 2,
                    val + err + max(vals_g) * 0.02,
                    _fmt_dollars(val),
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                )

        # Gap annotation
        gap_pct = gr["gap_pct"]
        if pd.notna(gap_pct):
            mid_y = (vals_g[0] + vals_g[1]) / 2
            ax_gender.annotate(
                f"Gap: {gap_pct:.1f}%",
                xy=(1, vals_g[1]),
                xytext=(1.35, mid_y),
                fontsize=9, color=CLR_GAP_ANNOT, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=CLR_GAP_ANNOT, lw=1.0),
            )

        ax_gender.set_ylabel("Median Annual Earnings (2024 $)")
        ax_gender.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:,.0f}")
        )
        ax_gender.set_ylim(bottom=0)
        if n_panels == 2:
            ax_gender.set_title("(a) By Sex", fontsize=10)

    # ---- Panel B: Racial wage gaps ----
    if has_race and ax_race is not None:
        # NH White is always group_a in race comparisons
        white_med = race_rows.iloc[0]["group_a_median"]
        white_se = race_rows.iloc[0]["group_a_se"]

        r_labels = ["NH White"]
        r_vals = [white_med]
        r_errs = [1.96 * white_se if pd.notna(white_se) else 0]
        r_colors = [CLR_NH_WHITE]

        for _, rr in race_rows.iterrows():
            r_labels.append(rr["group_b"])
            r_vals.append(rr["group_b_median"])
            se_b = rr["group_b_se"]
            r_errs.append(1.96 * se_b if pd.notna(se_b) else 0)
            r_colors.append(RACE_CLR_MAP.get(rr["group_b"], CLR_NH_OTHER))

        x_pos = np.arange(len(r_labels))
        bars = ax_race.bar(
            x_pos, r_vals, yerr=r_errs, color=r_colors,
            width=0.5, edgecolor="white", capsize=4,
            error_kw={"linewidth": 0.8, "capthick": 0.8}, zorder=3,
        )

        ax_race.set_xticks(x_pos)
        ax_race.set_xticklabels(r_labels, rotation=25, ha="right")

        # Dollar labels above bars
        for bar_obj, val, err in zip(bars, r_vals, r_errs):
            if pd.notna(val):
                ax_race.text(
                    bar_obj.get_x() + bar_obj.get_width() / 2,
                    val + err + max(v for v in r_vals if pd.notna(v)) * 0.02,
                    _fmt_dollars(val),
                    ha="center", va="bottom", fontsize=9, fontweight="bold",
                )

        # Gap percentage annotations for non-reference groups
        for j, (_, rr) in enumerate(race_rows.iterrows()):
            gap_pct = rr["gap_pct"]
            comp_val = rr["group_b_median"]
            if pd.isna(gap_pct) or pd.isna(comp_val):
                continue
            bar_idx = j + 1  # offset by 1 for NH White
            ax_race.text(
                bar_idx, comp_val * 0.55,
                f"\u2193 {gap_pct:.1f}%",
                ha="center", va="top", fontsize=8,
                color=CLR_GAP_ANNOT, fontstyle="italic",
            )

        ax_race.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:,.0f}")
        )
        ax_race.set_ylim(bottom=0)
        if n_panels == 2:
            ax_race.set_title("(b) By Race / Ethnicity", fontsize=10)
        if not has_gender:
            ax_race.set_ylabel("Median Annual Earnings (2024 $)")

    fig.tight_layout()
    _save_fig(fig, outdir, "fig2_wage_gaps")


# ---------------------------------------------------------------------------
# Figure 3: Intersectional Composition -- Race x Sex Heatmap
# ---------------------------------------------------------------------------
RACE_ORDER = ["NH White", "Hispanic", "NH Black", "NH Asian", "NH Other"]
SEX_ORDER = ["Male", "Female"]


def figure3_intersectional_heatmap(inter_df: pd.DataFrame, outdir: Path):
    """Heatmap of weighted_pct for race x sex among Surveyors."""
    print("\nFigure 3: Intersectional composition heatmap")

    df = inter_df.copy()

    # Set suppressed cells to NaN for display
    df.loc[df["suppressed"] == True, "weighted_pct"] = np.nan

    # Filter to known categories
    df = df[df["race_eth"].isin(RACE_ORDER) & df["sex_r"].isin(SEX_ORDER)]

    if len(df) == 0:
        print("  WARNING: No intersectional data available; skipping Figure 3.")
        return

    # Pivot: race rows x sex columns
    pivot = df.pivot_table(
        index="race_eth", columns="sex_r",
        values="weighted_pct", aggfunc="first",
    )

    # Also get suppression flags
    supp_pivot = inter_df.pivot_table(
        index="race_eth", columns="sex_r",
        values="suppressed", aggfunc="first",
    )

    # Reorder
    row_order = [r for r in RACE_ORDER if r in pivot.index]
    col_order = [c for c in SEX_ORDER if c in pivot.columns]
    pivot = pivot.reindex(index=row_order, columns=col_order)
    supp_pivot = supp_pivot.reindex(index=row_order, columns=col_order).fillna(True)

    fig, ax = plt.subplots(figsize=(FIG_W * 0.75, FIG_H * 0.85))

    # Sequential colorblind-friendly colormap
    cmap = sns.color_palette("YlOrBr", as_cmap=True)

    # Mask NaN cells (suppressed)
    mask = pivot.isna()

    sns.heatmap(
        pivot,
        ax=ax,
        cmap=cmap,
        mask=mask,
        annot=False,
        linewidths=1.5,
        linecolor="white",
        cbar_kws={
            "label": "Share of Surveyors (%)",
            "shrink": 0.7,
        },
        vmin=0,
        square=False,
    )

    # Manual cell annotations
    for i, race in enumerate(row_order):
        for j, sex in enumerate(col_order):
            val = pivot.loc[race, sex] if (race in pivot.index and sex in pivot.columns) else np.nan
            is_supp = bool(supp_pivot.loc[race, sex]) if (race in supp_pivot.index and sex in supp_pivot.columns) else True

            if is_supp or pd.isna(val):
                ax.text(
                    j + 0.5, i + 0.5, "n < 50",
                    ha="center", va="center", fontsize=9,
                    color="#888888", fontstyle="italic",
                )
            else:
                text_color = "white" if val > 30 else "black"
                ax.text(
                    j + 0.5, i + 0.5, f"{val:.1f}%",
                    ha="center", va="center", fontsize=10,
                    fontweight="bold", color=text_color,
                )

    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    fig.tight_layout()
    _save_fig(fig, outdir, "fig3_intersectional_heatmap")


# ---------------------------------------------------------------------------
# Figure 4: Metro vs Non-Metro Diversity Comparison
# ---------------------------------------------------------------------------
def figure4_metro_nonmetro(metro_df: pd.DataFrame, outdir: Path):
    """Grouped bar chart comparing diversity metrics between metro and
    non-metro surveyors."""
    print("\nFigure 4: Metro vs non-metro diversity comparison")

    metro_df = metro_df.copy()

    # Keep only Metro and Non-metro rows
    metro_df = metro_df[metro_df["metro_status"].isin(["Metro", "Non-metro"])]

    if len(metro_df) == 0:
        print("  WARNING: No metro/non-metro data; skipping Figure 4.")
        return

    metro_row = metro_df[metro_df["metro_status"] == "Metro"]
    nonmetro_row = metro_df[metro_df["metro_status"] == "Non-metro"]

    if len(metro_row) == 0 or len(nonmetro_row) == 0:
        print("  WARNING: Incomplete metro/non-metro data; skipping Figure 4.")
        return

    m = metro_row.iloc[0]
    nm = nonmetro_row.iloc[0]

    # Determine which metrics are available
    metric_specs = [
        ("pct_nonwhite", "% Non-White"),
        ("pct_female", "% Female"),
        ("pct_55plus", "% Aged 55+"),
    ]
    metrics = []
    metric_labels = []
    for col, label in metric_specs:
        if col in m.index and col in nm.index:
            mv = m[col]
            nmv = nm[col]
            if pd.notna(mv) and pd.notna(nmv):
                metrics.append(col)
                metric_labels.append(label)

    if not metrics:
        print("  WARNING: Expected columns not found; skipping Figure 4.")
        return

    metro_vals = [m[col] for col in metrics]
    nonmetro_vals = [nm[col] for col in metrics]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    x_pos = np.arange(len(metrics))
    bar_w = 0.32

    bars_m = ax.bar(
        x_pos - bar_w / 2, metro_vals,
        width=bar_w, color=CLR_METRO, edgecolor="white",
        label="Metro", zorder=3,
    )
    bars_nm = ax.bar(
        x_pos + bar_w / 2, nonmetro_vals,
        width=bar_w, color=CLR_NONMETRO, edgecolor="white",
        label="Non-Metro", zorder=3,
    )

    # Value labels on each bar
    for i, (mv, nmv) in enumerate(zip(metro_vals, nonmetro_vals)):
        if pd.notna(mv):
            ax.text(
                i - bar_w / 2, mv + 0.5, f"{mv:.1f}%",
                ha="center", va="bottom", fontsize=8.5, fontweight="bold",
            )
        if pd.notna(nmv):
            ax.text(
                i + bar_w / 2, nmv + 0.5, f"{nmv:.1f}%",
                ha="center", va="bottom", fontsize=8.5, fontweight="bold",
            )

    # Gap annotations
    for i, (mv, nmv) in enumerate(zip(metro_vals, nonmetro_vals)):
        if pd.notna(mv) and pd.notna(nmv):
            gap = mv - nmv
            sign = "+" if gap >= 0 else ""
            higher = max(mv, nmv)
            ax.text(
                i, higher + 3.5,
                f"Gap: {sign}{gap:.1f} pp",
                ha="center", va="bottom", fontsize=8,
                color=CLR_GAP_ANNOT, fontstyle="italic",
            )

    ax.set_xticks(x_pos)
    ax.set_xticklabels(metric_labels)
    ax.set_ylabel("Share of Surveyors (%)")
    ax.set_ylim(bottom=0)

    # Give room for gap annotations
    all_vals = [v for v in metro_vals + nonmetro_vals if pd.notna(v)]
    if all_vals:
        ax.set_ylim(top=max(all_vals) + 12)

    ax.legend(loc="upper right", frameon=True, framealpha=0.9,
              edgecolor="#CCCCCC")

    fig.tight_layout()
    _save_fig(fig, outdir, "fig4_metro_nonmetro")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 6B: Publication-ready figures for Paper 2 "
                    "(Demographic Disparity and Earnings Gaps)"
    )
    parser.add_argument(
        "--indir", default="analysis/p2",
        help="Directory containing Paper 2 analysis CSVs (default: analysis/p2)",
    )
    parser.add_argument(
        "--outdir", default="figures/p2",
        help="Output directory for figures (default: figures/p2)",
    )
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)

    if not indir.exists():
        print(f"ERROR: Input directory does not exist: {indir}")
        print("Run s4b_disparity_analysis.py, s4c_earnings_analysis.py, and "
              "s4d_geographic_analysis.py first to generate Paper 2 CSVs.")
        sys.exit(1)

    outdir.mkdir(parents=True, exist_ok=True)

    # Apply APA-compatible style
    plt.rcParams.update(APA_RC)

    # ------------------------------------------------------------------
    # Load CSVs (handle missing files gracefully)
    # ------------------------------------------------------------------
    csv_files = {
        "representation": ("p2_representation_ratios.csv", "Figure 1"),
        "wage_gaps":      ("p2_wage_gaps.csv",             "Figure 2"),
        "intersectional": ("p2_intersectional.csv",        "Figure 3"),
        "metro":          ("p2_metro_nonmetro.csv",        "Figure 4"),
    }

    data = {}
    for key, (filename, fig_label) in csv_files.items():
        path = indir / filename
        if path.exists():
            df = pd.read_csv(path)
            data[key] = df
            print(f"Loaded {path} ({len(df)} rows)")
        else:
            data[key] = None
            print(f"WARNING: {path} not found. {fig_label} will be skipped.")

    # ------------------------------------------------------------------
    # Generate figures
    # ------------------------------------------------------------------
    n_produced = 0

    # Figure 1: Representation ratios
    if data["representation"] is not None and len(data["representation"]) > 0:
        try:
            figure1_representation_ratios(data["representation"], outdir)
            n_produced += 1
        except Exception as e:
            print(f"  ERROR generating Figure 1: {e}")

    # Figure 2: Wage gaps
    if data["wage_gaps"] is not None and len(data["wage_gaps"]) > 0:
        try:
            figure2_wage_gaps(data["wage_gaps"], outdir)
            n_produced += 1
        except Exception as e:
            print(f"  ERROR generating Figure 2: {e}")

    # Figure 3: Intersectional heatmap
    if data["intersectional"] is not None and len(data["intersectional"]) > 0:
        try:
            figure3_intersectional_heatmap(data["intersectional"], outdir)
            n_produced += 1
        except Exception as e:
            print(f"  ERROR generating Figure 3: {e}")

    # Figure 4: Metro vs non-metro
    if data["metro"] is not None and len(data["metro"]) > 0:
        try:
            figure4_metro_nonmetro(data["metro"], outdir)
            n_produced += 1
        except Exception as e:
            print(f"  ERROR generating Figure 4: {e}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("PAPER 2 FIGURES COMPLETE")
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
