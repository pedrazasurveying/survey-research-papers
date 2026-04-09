"""
Subagent 5B: TABLE_BUILD — Paper 2
====================================
Read Paper 2 analysis CSVs and produce APA 7 formatted .docx tables.

Usage:
    python scripts/s5b_tables_p2.py
    python scripts/s5b_tables_p2.py --indir analysis/p2 --outdir tables/p2
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ---------------------------------------------------------------------------
# APA 7 table helpers
# ---------------------------------------------------------------------------
FONT_NAME = "Times New Roman"
BODY_SIZE = Pt(11)
TITLE_SIZE = Pt(12)
NOTE_SIZE = Pt(10)


def set_cell_font(cell, text, bold=False, italic=False, size=BODY_SIZE,
                  alignment=WD_ALIGN_PARAGRAPH.CENTER):
    """Set cell text with consistent formatting."""
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = alignment
    run = p.add_run(str(text))
    run.font.name = FONT_NAME
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    # Set east-asian font
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{FONT_NAME}"/>')
        rPr.append(rFonts)


def set_cell_borders(cell, top=None, bottom=None, left=None, right=None):
    """Set individual cell borders."""
    tc = cell._element
    tcPr = tc.find(qn("w:tcPr"))
    if tcPr is None:
        tcPr = parse_xml(f'<w:tcPr {nsdecls("w")}/>')
        tc.insert(0, tcPr)
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = parse_xml(f'<w:tcBorders {nsdecls("w")}/>')
        tcPr.append(borders)

    for side, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        if val is not None:
            border = parse_xml(
                f'<w:{side} {nsdecls("w")} w:val="{val}" w:sz="4" w:space="0" w:color="000000"/>'
            )
            existing = borders.find(qn(f"w:{side}"))
            if existing is not None:
                borders.remove(existing)
            borders.append(border)


def apa_table_lines(table, n_header_rows=1):
    """Apply APA 7 border rules: top, below header, bottom only."""
    for i, row in enumerate(table.rows):
        for cell in row.cells:
            if i == 0:
                set_cell_borders(cell, top="single", bottom="single",
                                 left="none", right="none")
            elif i == n_header_rows - 1:
                set_cell_borders(cell, bottom="single", left="none",
                                 right="none", top="none")
            elif i == len(table.rows) - 1:
                set_cell_borders(cell, bottom="single", left="none",
                                 right="none", top="none")
            else:
                set_cell_borders(cell, top="none", bottom="none",
                                 left="none", right="none")


def add_table_note(doc, text):
    """Add an APA 7 table note paragraph."""
    p = doc.add_paragraph()
    run = p.add_run(f"Note. {text}")
    run.font.name = FONT_NAME
    run.font.size = NOTE_SIZE
    run.font.italic = True


def add_table_title(doc, number, title):
    """Add APA 7 table title."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(f"Table {number}")
    run.font.name = FONT_NAME
    run.font.size = TITLE_SIZE
    run.font.bold = True
    run.font.italic = True
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run2 = p2.add_run(title)
    run2.font.name = FONT_NAME
    run2.font.size = TITLE_SIZE
    run2.font.italic = True


def fmt_pct(val):
    """Format percentage to 1 decimal."""
    if pd.isna(val):
        return "—"
    return f"{val:.1f}"


def fmt_n(val):
    """Format count with comma separator."""
    if pd.isna(val):
        return "—"
    return f"{val:,.0f}"


def fmt_dollar(val):
    """Format dollar amount."""
    if pd.isna(val):
        return "—"
    return f"${val:,.0f}"


def fmt_ci(median, ci_lo, ci_hi):
    """Format median with 95% CI."""
    if pd.isna(median):
        return "—"
    if pd.isna(ci_lo) or pd.isna(ci_hi):
        return fmt_dollar(median)
    return f"${median:,.0f} [{ci_lo:,.0f}, {ci_hi:,.0f}]"


def fmt_pval(p):
    """Format p-value with significance stars."""
    if pd.isna(p):
        return "—"
    if p < 0.001:
        return "< .001***"
    elif p < 0.01:
        return f"{p:.3f}**"
    elif p < 0.05:
        return f"{p:.3f}*"
    else:
        return f"{p:.3f}"


def load_csv(path):
    """Load CSV, return None if missing."""
    if not path.exists():
        print(f"  WARNING: {path.name} not found. Skipping.")
        return None
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------
def build_table1(doc, composition, chi2_df):
    """Table 1: Demographic Composition."""
    add_table_title(doc, 1, "Demographic Composition of Surveyors and Survey Technicians")

    # Build panels
    panels = [
        ("A", "Race/Ethnicity", "race_eth"),
        ("B", "Sex", "sex_r"),
        ("C", "Education", "educ_r"),
        ("D", "Veteran Status", "veteran"),
    ]

    headers = ["Category", "Surveyors % (SE)", "Technicians % (SE)", "n (Surv.)", "n (Tech.)"]
    rows_data = []

    for panel_letter, panel_label, var in panels:
        rows_data.append((f"Panel {panel_letter}: {panel_label}", "", "", "", ""))

        surv = composition[(composition["variable"] == var) & (composition["occupation"] == "Surveyors")]
        tech = composition[(composition["variable"] == var) & (composition["occupation"] == "Technicians")]

        # Get all categories from both
        cats = list(surv["category"].unique())
        for cat in tech["category"].unique():
            if cat not in cats:
                cats.append(cat)

        for cat in cats:
            s_row = surv[surv["category"] == cat]
            t_row = tech[tech["category"] == cat]

            s_pct = f"{s_row.iloc[0]['weighted_pct']:.1f} ({s_row.iloc[0]['se']:.2f})" if len(s_row) > 0 else "—"
            t_pct = f"{t_row.iloc[0]['weighted_pct']:.1f} ({t_row.iloc[0]['se']:.2f})" if len(t_row) > 0 else "—"
            s_n = fmt_n(s_row.iloc[0]["unweighted_n"]) if len(s_row) > 0 else "—"
            t_n = fmt_n(t_row.iloc[0]["unweighted_n"]) if len(t_row) > 0 else "—"

            rows_data.append((f"  {cat}", s_pct, t_pct, s_n, t_n))

        # Add chi-square result if available
        if chi2_df is not None and len(chi2_df) > 0:
            chi_row = chi2_df[chi2_df["variable"] == var]
            if len(chi_row) > 0:
                p = chi_row.iloc[0]["p_value"]
                chi2_val = chi_row.iloc[0]["chi2"]
                dof = chi_row.iloc[0]["dof"]
                sig = fmt_pval(p)
                rows_data.append((f"  χ²({dof:.0f}) = {chi2_val:.1f}, p {sig}", "", "", "", ""))

    # Create table
    n_rows = len(rows_data) + 1  # +1 for header
    table = doc.add_table(rows=n_rows, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header
    for j, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], h, bold=True, alignment=align)

    # Data
    for i, row_data in enumerate(rows_data):
        for j, val in enumerate(row_data):
            is_panel = val.startswith("Panel")
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            set_cell_font(table.rows[i + 1].cells[j], val, bold=is_panel, alignment=align)

    apa_table_lines(table)

    add_table_note(doc,
        "Weighted percentages with BRR standard errors (Fay k = 0.5) in parentheses. "
        "n = unweighted sample size. Chi-square tests compare composition between "
        "surveyors and technicians. Data: ACS 2020–2024 5-year IPUMS microdata. "
        "***p < .001, **p < .01, *p < .05.")

    doc.add_page_break()


def build_table2(doc, ratios):
    """Table 2: Representation Ratios."""
    add_table_title(doc, 2, "Representation of Surveyors Relative to U.S. Workforce")

    headers = ["Demographic Group", "Surveyor %", "U.S. Workforce %",
               "Representation Ratio", "Assessment"]

    n_rows = len(ratios) + 1
    table = doc.add_table(rows=n_rows, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], h, bold=True, alignment=align)

    for i, (_, row) in enumerate(ratios.iterrows()):
        cat = row["category"]
        s_pct = fmt_pct(row["surveyor_pct"])
        us_pct = fmt_pct(row["us_workforce_pct"])
        ratio = f"{row['representation_ratio']:.2f}" if not pd.isna(row["representation_ratio"]) else "—"
        flag = row.get("flag", "")
        if not flag:
            if not pd.isna(row["representation_ratio"]):
                if row["representation_ratio"] >= 0.8:
                    flag = "Near parity"
                elif row["representation_ratio"] >= 1.2:
                    flag = "Overrepresented"

        set_cell_font(table.rows[i + 1].cells[0], cat, alignment=WD_ALIGN_PARAGRAPH.LEFT)
        set_cell_font(table.rows[i + 1].cells[1], s_pct)
        set_cell_font(table.rows[i + 1].cells[2], us_pct)
        set_cell_font(table.rows[i + 1].cells[3], ratio)
        set_cell_font(table.rows[i + 1].cells[4], flag, alignment=WD_ALIGN_PARAGRAPH.LEFT)

    apa_table_lines(table)

    add_table_note(doc,
        "Representation ratio = surveyor share / U.S. workforce share. "
        "Ratios below 0.50 indicate severe underrepresentation; 0.50–0.80 indicate "
        "underrepresentation; 0.80–1.20 indicate near parity. "
        "Data: ACS 2020–2024 5-year IPUMS microdata.")

    doc.add_page_break()


def build_table3(doc, wage_gaps, earnings_core):
    """Table 3: Median Annual Earnings and Wage Gaps."""
    add_table_title(doc, 3, "Median Annual Earnings by Demographic Group, Surveyors (OCC 1310)")

    headers = ["Group", "Median Earnings (95% CI)", "n", "Gap ($)", "Gap (%)"]

    # Core earnings for surveyors
    rows_data = []

    # Overall surveyor annual
    if earnings_core is not None:
        surv_annual = earnings_core[
            (earnings_core["measure"] == "wage_adj") &
            (earnings_core["group"].str.contains("Surveyors", na=False))
        ]
        if len(surv_annual) > 0:
            r = surv_annual.iloc[0]
            ci_str = fmt_ci(r["median"], r["ci_lower"], r["ci_upper"])
            rows_data.append(("All surveyors", ci_str, fmt_n(r["unweighted_n"]), "—", "—"))

    # Gender gap
    if wage_gaps is not None:
        gender = wage_gaps[
            (wage_gaps["comparison"].str.contains("Gender", na=False)) &
            (wage_gaps["occupation"] == "Surveyors")
        ]
        if len(gender) > 0:
            rows_data.append(("Gender", "", "", "", ""))
            g = gender.iloc[0]
            if not g["suppressed"]:
                rows_data.append((
                    f"  Male",
                    fmt_ci(g["group_a_median"], None, None),
                    fmt_n(g["group_a_n"]),
                    "ref.", "ref."
                ))
                rows_data.append((
                    f"  Female",
                    fmt_ci(g["group_b_median"], None, None),
                    fmt_n(g["group_b_n"]),
                    fmt_dollar(g["gap_dollars"]),
                    f"{g['gap_pct']:.1f}%"
                ))

        # Racial gaps
        racial = wage_gaps[
            (wage_gaps["comparison"].str.contains("Race", na=False)) &
            (wage_gaps["occupation"] == "Surveyors")
        ]
        if len(racial) > 0:
            rows_data.append(("Race/Ethnicity", "", "", "", ""))
            # Add NH White as reference
            first = racial.iloc[0]
            rows_data.append((
                "  NH White",
                fmt_ci(first["group_a_median"], None, None),
                fmt_n(first["group_a_n"]),
                "ref.", "ref."
            ))

            for _, r in racial.iterrows():
                if r["suppressed"]:
                    rows_data.append((
                        f"  {r['group_b']}",
                        "— [suppressed]",
                        fmt_n(r["group_b_n"]),
                        "—", "—"
                    ))
                else:
                    rows_data.append((
                        f"  {r['group_b']}",
                        fmt_ci(r["group_b_median"], None, None),
                        fmt_n(r["group_b_n"]),
                        fmt_dollar(r["gap_dollars"]),
                        f"{r['gap_pct']:.1f}%"
                    ))

        # Veteran
        veteran = wage_gaps[wage_gaps["comparison"].str.contains("Veteran", na=False)]
        if len(veteran) > 0:
            rows_data.append(("Veteran Status", "", "", "", ""))
            for _, r in veteran.iterrows():
                rows_data.append((
                    f"  {r['group_a']}",
                    fmt_ci(r["group_a_median"], None, None),
                    fmt_n(r["group_a_n"]),
                    "—", "—"
                ))

    n_rows = len(rows_data) + 1
    table = doc.add_table(rows=n_rows, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], h, bold=True, alignment=align)

    for i, row_data in enumerate(rows_data):
        is_section = row_data[0] in ("Gender", "Race/Ethnicity", "Veteran Status")
        for j, val in enumerate(row_data):
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            set_cell_font(table.rows[i + 1].cells[j], val, bold=is_section, alignment=align)

    apa_table_lines(table)

    add_table_note(doc,
        "Weighted median annual earnings in 2024 dollars (CPI-U adjusted). "
        "95% confidence intervals computed via BRR Woodruff method (Fay k = 0.5). "
        "Gap = reference group median − comparison group median. "
        "Cells with n < 50 are suppressed. "
        "Data: ACS 2020–2024 5-year IPUMS microdata.")

    doc.add_page_break()


def build_table4(doc, regression):
    """Table 4: OLS Regression Results."""
    add_table_title(doc, 4, "OLS Regression of Log Hourly Wage, Surveyors (OCC 1310)")

    headers = ["Variable", "Coefficient", "SE", "t", "p"]

    # Filter to coefficient rows (not model summary)
    coef_rows = regression[regression["variable"].notna()].copy()
    # Separate model summary row
    summary = regression[regression["variable"].isna() | (regression["variable"] == "")]

    rows_data = []
    for _, r in coef_rows.iterrows():
        var_name = r.get("variable", "")
        if pd.isna(var_name) or var_name == "":
            continue
        coef = f"{r['coefficient']:.4f}" if not pd.isna(r.get("coefficient")) else "—"
        se = f"{r['se']:.4f}" if not pd.isna(r.get("se")) else "—"
        t_val = f"{r['t_stat']:.2f}" if not pd.isna(r.get("t_stat")) else "—"
        p_val = fmt_pval(r.get("p_value")) if not pd.isna(r.get("p_value")) else "—"
        rows_data.append((var_name, coef, se, t_val, p_val))

    n_rows = len(rows_data) + 1
    table = doc.add_table(rows=n_rows, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], h, bold=True, alignment=align)

    for i, row_data in enumerate(rows_data):
        for j, val in enumerate(row_data):
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            set_cell_font(table.rows[i + 1].cells[j], val, alignment=align)

    apa_table_lines(table)

    # Model summary note
    note_parts = ["Dependent variable: log(hourly wage). HC1 robust standard errors. "
                  "State fixed effects (STATEFIP) included but not shown."]
    if len(summary) > 0:
        s = summary.iloc[0]
        if not pd.isna(s.get("r_squared")):
            note_parts.append(f"R² = {s['r_squared']:.3f}.")
        if not pd.isna(s.get("n_obs")):
            note_parts.append(f"N = {s['n_obs']:,.0f}.")

    note_parts.append("***p < .001, **p < .01, *p < .05.")
    add_table_note(doc, " ".join(note_parts))

    doc.add_page_break()


def build_table5(doc, state_comp, metro):
    """Table 5: Geographic Variation."""
    add_table_title(doc, 5, "Geographic Variation in Surveyor Demographics, Top States by Employment")

    headers = ["State", "N (weighted)", "% Non-White", "% Female", "Median Wage"]

    # Sort by weighted_n, take top 10
    top = state_comp.nlargest(10, "weighted_n") if len(state_comp) > 10 else state_comp

    rows_data = []
    for _, r in top.iterrows():
        state = r.get("state_name", r.get("state", ""))
        n = fmt_n(r.get("weighted_n", np.nan))
        nw = fmt_pct(r.get("pct_nonwhite", np.nan))
        fem = fmt_pct(r.get("pct_female", np.nan))
        wage = fmt_dollar(r.get("median_wage_adj", np.nan))
        rows_data.append((state, n, nw, fem, wage))

    # Add metro/non-metro summary if available
    if metro is not None and len(metro) > 0:
        rows_data.append(("", "", "", "", ""))
        for _, r in metro.iterrows():
            label = r.get("metro_status", "")
            n = fmt_n(r.get("weighted_n", np.nan))
            nw = fmt_pct(r.get("pct_nonwhite", np.nan))
            fem = fmt_pct(r.get("pct_female", np.nan))
            wage = fmt_dollar(r.get("median_wage_adj", np.nan))
            rows_data.append((label, n, nw, fem, wage))

    n_rows = len(rows_data) + 1
    table = doc.add_table(rows=n_rows, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for j, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], h, bold=True, alignment=align)

    for i, row_data in enumerate(rows_data):
        for j, val in enumerate(row_data):
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            set_cell_font(table.rows[i + 1].cells[j], val, alignment=align)

    apa_table_lines(table)

    add_table_note(doc,
        "Top 10 states by weighted surveyor employment. States with unweighted n < 30 "
        "are suppressed. Median wage in 2024 dollars. Metro/non-metro classification "
        "based on IPUMS METRO variable. Data: ACS 2020–2024 5-year IPUMS microdata.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Subagent 5B: TABLE_BUILD — Paper 2")
    parser.add_argument("--indir", default="analysis/p2",
                        help="Input directory with analysis CSVs")
    parser.add_argument("--outdir", default="tables/p2",
                        help="Output directory for .docx tables")
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not indir.exists():
        print(f"ERROR: Input directory not found: {indir}")
        print("Run s4b, s4c, s4d analysis scripts first.")
        sys.exit(1)

    print(f"Loading Paper 2 analysis from: {indir}")

    # Load all CSVs
    composition = load_csv(indir / "p2_composition.csv")
    chi2_df = load_csv(indir / "p2_composition_chi2.csv")
    ratios = load_csv(indir / "p2_representation_ratios.csv")
    earnings_core = load_csv(indir / "p2_earnings_core.csv")
    wage_gaps = load_csv(indir / "p2_wage_gaps.csv")
    regression = load_csv(indir / "p2_wage_regression.csv")
    state_comp = load_csv(indir / "p2_state_composition.csv")
    metro = load_csv(indir / "p2_metro_nonmetro.csv")

    tables_built = 0

    # Table 1: Demographic Composition
    if composition is not None:
        doc = Document()
        build_table1(doc, composition, chi2_df)
        out = outdir / "Table1_Composition.docx"
        doc.save(out)
        print(f"  Table 1 saved: {out}")
        tables_built += 1

    # Table 2: Representation Ratios
    if ratios is not None:
        doc = Document()
        build_table2(doc, ratios)
        out = outdir / "Table2_Representation.docx"
        doc.save(out)
        print(f"  Table 2 saved: {out}")
        tables_built += 1

    # Table 3: Earnings and Wage Gaps
    if wage_gaps is not None:
        doc = Document()
        build_table3(doc, wage_gaps, earnings_core)
        out = outdir / "Table3_Earnings.docx"
        doc.save(out)
        print(f"  Table 3 saved: {out}")
        tables_built += 1

    # Table 4: Regression
    if regression is not None:
        doc = Document()
        build_table4(doc, regression)
        out = outdir / "Table4_Regression.docx"
        doc.save(out)
        print(f"  Table 4 saved: {out}")
        tables_built += 1

    # Table 5: Geographic
    if state_comp is not None:
        doc = Document()
        build_table5(doc, state_comp, metro)
        out = outdir / "Table5_Geographic.docx"
        doc.save(out)
        print(f"  Table 5 saved: {out}")
        tables_built += 1

    print(f"\nDone. {tables_built} tables saved to {outdir}/")


if __name__ == "__main__":
    main()
