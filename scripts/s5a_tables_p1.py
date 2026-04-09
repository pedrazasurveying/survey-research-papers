"""
Subagent 5A: TABLES_P1
========================
Read Paper 1 analysis CSV outputs (age distribution, retirement cliff,
geographic aging) and produce APA 7 formatted publication-ready tables as
.docx files for the workforce aging and contraction paper.

Tables produced:
    1. table1_age_distribution.docx   -- Age distribution by occupation and
                                         comparison group
    2. table2_retirement_cliff.docx   -- Retirement cliff indicators for
                                         surveyors (OCC 1310)
    3. table3_state_aging.docx        -- State-level age distribution of
                                         surveyors (top 15 by employment)

Usage:
    python scripts/s5a_tables_p1.py
    python scripts/s5a_tables_p1.py --indir analysis/p1 --outdir tables/p1
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FONT_BODY = "Times New Roman"
FONT_SIZE_BODY = Pt(11)
FONT_SIZE_TITLE = Pt(12)
FONT_SIZE_NOTE = Pt(10)

# Group display order for Table 1
GROUP_ORDER = [
    "Surveyors",
    "Survey technicians",
    "U.S. workforce",
    "All STEM",
    "Architecture & engineering",
    "Construction trades",
]


# ---------------------------------------------------------------------------
# Number formatting helpers
# ---------------------------------------------------------------------------
def fmt_n(val):
    """Format an integer N with comma-separated thousands, 0 decimals."""
    if pd.isna(val):
        return "\u2014"
    return f"{val:,.0f}"


def fmt_pct(val, decimals=1):
    """Format a percentage to *decimals* decimal places."""
    if pd.isna(val):
        return "\u2014"
    return f"{val:.{decimals}f}"


def fmt_dec(val, decimals=1):
    """Format a decimal value to *decimals* decimal places."""
    if pd.isna(val):
        return "\u2014"
    return f"{val:.{decimals}f}"


def fmt_ci(lo, hi, decimals=1):
    """Format a 95% CI as [lo, hi]."""
    if pd.isna(lo) or pd.isna(hi):
        return ""
    return f"[{lo:.{decimals}f}, {hi:.{decimals}f}]"


def fmt_se(val, decimals=2):
    """Format SE in parentheses: (x.xx)."""
    if pd.isna(val):
        return ""
    return f"({val:.{decimals}f})"


# ---------------------------------------------------------------------------
# APA 7 table formatting utilities
# ---------------------------------------------------------------------------
def set_cell_font(cell, text, font_name=FONT_BODY, font_size=FONT_SIZE_BODY,
                  bold=False, italic=False, alignment=WD_ALIGN_PARAGRAPH.CENTER):
    """Set the text and font properties for a table cell."""
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = alignment
    run = paragraph.add_run(text)
    run.font.name = font_name
    run.font.size = font_size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor(0, 0, 0)

    # Compact spacing: 0pt before/after
    pf = paragraph.paragraph_format
    pf.space_before = Pt(1)
    pf.space_after = Pt(1)


def remove_all_borders(table):
    """Remove all cell borders from a table (APA tables have no vertical
    lines and only specific horizontal rules)."""
    for row in table.rows:
        for cell in row.cells:
            tc_pr = cell._element.get_or_add_tcPr()
            borders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                '  <w:top w:val="nil"/>'
                '  <w:left w:val="nil"/>'
                '  <w:bottom w:val="nil"/>'
                '  <w:right w:val="nil"/>'
                '  <w:insideH w:val="nil"/>'
                '  <w:insideV w:val="nil"/>'
                '</w:tcBorders>'
            )
            tc_pr.append(borders)


def set_row_bottom_border(row, sz="4", color="000000"):
    """Add a bottom border to every cell in a row."""
    for cell in row.cells:
        tc_pr = cell._element.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:bottom w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            '</w:tcBorders>'
        )
        tc_pr.append(borders)


def set_row_top_border(row, sz="4", color="000000"):
    """Add a top border to every cell in a row."""
    for cell in row.cells:
        tc_pr = cell._element.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:top w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            '</w:tcBorders>'
        )
        tc_pr.append(borders)


def set_cell_shading(cell, color="FFFFFF"):
    """Set background color for a cell."""
    shading_elm = parse_xml(
        f'<w:shd {nsdecls("w")} w:fill="{color}" w:val="clear"/>'
    )
    cell._element.get_or_add_tcPr().append(shading_elm)


def create_apa_document():
    """Create a Document with APA 7 default styles."""
    doc = Document()

    # Set narrow margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = FONT_BODY
    font.size = FONT_SIZE_BODY
    font.color.rgb = RGBColor(0, 0, 0)

    return doc


def add_table_title(doc, table_number, title_text):
    """Add an APA 7 table title (Table N in bold italic, then title in italic)."""
    # "Table N" line -- bold italic
    p_label = doc.add_paragraph()
    p_label.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_label.paragraph_format.space_after = Pt(0)
    run_label = p_label.add_run(f"Table {table_number}")
    run_label.font.name = FONT_BODY
    run_label.font.size = FONT_SIZE_TITLE
    run_label.font.bold = True
    run_label.font.italic = True
    run_label.font.color.rgb = RGBColor(0, 0, 0)

    # Title line -- italic
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(6)
    run_title = p_title.add_run(title_text)
    run_title.font.name = FONT_BODY
    run_title.font.size = FONT_SIZE_TITLE
    run_title.font.italic = True
    run_title.font.color.rgb = RGBColor(0, 0, 0)


def add_table_note(doc, note_text):
    """Add an APA 7 table note in 10pt italic."""
    p_note = doc.add_paragraph()
    p_note.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_note.paragraph_format.space_before = Pt(6)

    # "Note. " in italic bold
    run_label = p_note.add_run("Note. ")
    run_label.font.name = FONT_BODY
    run_label.font.size = FONT_SIZE_NOTE
    run_label.font.italic = True
    run_label.font.bold = False
    run_label.font.color.rgb = RGBColor(0, 0, 0)

    # Note body in italic
    run_body = p_note.add_run(note_text)
    run_body.font.name = FONT_BODY
    run_body.font.size = FONT_SIZE_NOTE
    run_body.font.italic = True
    run_body.font.color.rgb = RGBColor(0, 0, 0)


def finalize_apa_table(table, header_row_idx=0):
    """Apply APA 7 formatting to a python-docx table:
    - Remove all borders
    - Add horizontal rule at top of header, below header, and at bottom
    - No vertical lines
    """
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Remove all borders first
    remove_all_borders(table)

    # Top border on header row
    set_row_top_border(table.rows[header_row_idx], sz="8")

    # Bottom border on header row
    set_row_bottom_border(table.rows[header_row_idx], sz="4")

    # Bottom border on last row
    last_row = table.rows[-1]
    set_row_bottom_border(last_row, sz="8")


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------
def build_table1(indir: Path, outdir: Path) -> str | None:
    """Table 1: Age Distribution by Occupation and Comparison Group."""
    csv_path = indir / "p1_age_distribution.csv"
    if not csv_path.exists():
        warnings.warn(f"File not found, skipping Table 1: {csv_path}")
        return None

    df = pd.read_csv(csv_path)

    # Order rows according to GROUP_ORDER; keep any extras at the end
    ordered = []
    for g in GROUP_ORDER:
        match = df[df["group"] == g]
        if len(match) > 0:
            ordered.append(match.iloc[0])
    # Append any groups not in GROUP_ORDER
    seen = {g for g in GROUP_ORDER}
    for _, row in df.iterrows():
        if row["group"] not in seen:
            ordered.append(row)
    if not ordered:
        warnings.warn("No data rows found in p1_age_distribution.csv")
        return None

    doc = create_apa_document()

    add_table_title(
        doc, 1,
        "Age Distribution of Surveyors, Survey Technicians, and Comparison Groups, "
        "ACS 2020\u20132024"
    )

    # Column headers
    headers = [
        "Group",
        "N (weighted)",
        "Median Age\n(95% CI)",
        "% Aged\n18\u201334",
        "% Aged\n55+",
        "% Aged\n65+",
    ]

    n_rows = len(ordered) + 1  # +1 for header
    n_cols = len(headers)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.autofit = True

    # Header row
    for j, hdr in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], hdr, bold=True, alignment=align)

    # Data rows
    for i, row_data in enumerate(ordered):
        r = i + 1  # row index in table (0 is header)
        row = table.rows[r]

        # Group name (left aligned)
        set_cell_font(row.cells[0], str(row_data["group"]),
                      alignment=WD_ALIGN_PARAGRAPH.LEFT)

        # N (weighted)
        set_cell_font(row.cells[1], fmt_n(row_data.get("weighted_n")))

        # Median Age (95% CI)
        med = row_data.get("median_age")
        se = row_data.get("median_age_SE")
        ci_lo = row_data.get("median_age_CI_lo")
        ci_hi = row_data.get("median_age_CI_hi")
        if pd.notna(med):
            age_str = fmt_dec(med, 1)
            ci_str = fmt_ci(ci_lo, ci_hi, 1)
            if ci_str:
                age_str += f" {ci_str}"
            se_str = fmt_se(se)
            if se_str:
                age_str += f"\n{se_str}"
            set_cell_font(row.cells[2], age_str)
        else:
            set_cell_font(row.cells[2], "\u2014")

        # Percentages
        set_cell_font(row.cells[3], fmt_pct(row_data.get("pct_18_34")))
        set_cell_font(row.cells[4], fmt_pct(row_data.get("pct_55plus")))
        set_cell_font(row.cells[5], fmt_pct(row_data.get("pct_65plus")))

    finalize_apa_table(table)

    # Table note
    add_table_note(
        doc,
        "Data from the American Community Survey (ACS) 2020\u20132024, 5-year "
        "Public Use Microdata Sample (PUMS) via IPUMS USA. Surveyors = OCC 1310; "
        "Survey technicians = OCC 1560. Standard errors estimated using Fay\u2019s "
        "Balanced Repeated Replication (BRR) with perturbation factor k = 0.5 and "
        "80 ACS replicate weights. 95% confidence intervals calculated as "
        "estimate \u00b1 1.96 \u00d7 SE. SE shown in parentheses below the "
        "median age estimate. Comparison groups (U.S. workforce, All STEM, "
        "Architecture & engineering, Construction trades) are computed from "
        "pooled ACS microdata using person-level weights; BRR SE is not "
        "available for these benchmarks. N = weighted population estimate; "
        "percentages are weighted."
    )

    out_path = outdir / "table1_age_distribution.docx"
    doc.save(str(out_path))
    return str(out_path)


def build_table2(indir: Path, outdir: Path) -> str | None:
    """Table 2: Retirement Cliff Indicators for Surveyors (OCC 1310)."""
    csv_path = indir / "p1_retirement_cliff.csv"
    if not csv_path.exists():
        warnings.warn(f"File not found, skipping Table 2: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    if len(df) == 0:
        warnings.warn("Empty data in p1_retirement_cliff.csv, skipping Table 2")
        return None

    doc = create_apa_document()

    add_table_title(
        doc, 2,
        "Retirement Cliff Indicators for Surveyors (OCC 1310), ACS 2020\u20132024"
    )

    headers = ["Metric", "Estimate", "SE", "95% CI"]
    n_rows = len(df) + 1
    n_cols = len(headers)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.autofit = True

    # Header
    for j, hdr in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], hdr, bold=True, alignment=align)

    # Data rows
    for i, (_, row_data) in enumerate(df.iterrows()):
        r = i + 1
        row = table.rows[r]
        metric = str(row_data["metric"])

        # Metric name (left aligned)
        set_cell_font(row.cells[0], metric,
                      alignment=WD_ALIGN_PARAGRAPH.LEFT)

        # Determine whether value is a count (N) or a percentage/years
        val = row_data["value"]
        is_count = any(kw in metric.lower() for kw in
                       ["weighted n", "total surveyor workforce"])

        if is_count:
            val_str = fmt_n(val)
        else:
            val_str = fmt_dec(val, 1)

        set_cell_font(row.cells[1], val_str)

        # SE
        se = row_data.get("SE")
        if pd.notna(se):
            set_cell_font(row.cells[2], fmt_dec(se, 2))
        else:
            set_cell_font(row.cells[2], "\u2014")

        # 95% CI
        ci_lo = row_data.get("CI_95_lo")
        ci_hi = row_data.get("CI_95_hi")
        if pd.notna(ci_lo) and pd.notna(ci_hi):
            set_cell_font(row.cells[3], fmt_ci(ci_lo, ci_hi, 1))
        else:
            set_cell_font(row.cells[3], "\u2014")

    finalize_apa_table(table)

    add_table_note(
        doc,
        "Data from the American Community Survey (ACS) 2020\u20132024, 5-year "
        "PUMS via IPUMS USA. Surveyors identified by OCC = 1310. Percentages "
        "are weighted using ACS person weights (PERWT). Standard errors "
        "estimated via Fay\u2019s BRR (k = 0.5, 80 replicate weights). "
        "Retirement cliff gap = percentage of workforce aged 55+ minus "
        "percentage aged 18\u201334; a positive value indicates more workers "
        "approaching retirement than entering the profession. Years to "
        "retirement assume a retirement age of 65. CI = confidence interval; "
        "SE = standard error. An em dash (\u2014) indicates that the statistic "
        "is not applicable or not estimable for that metric."
    )

    out_path = outdir / "table2_retirement_cliff.docx"
    doc.save(str(out_path))
    return str(out_path)


def build_table3(indir: Path, outdir: Path) -> str | None:
    """Table 3: State-Level Age Distribution of Surveyors (top 15)."""
    csv_path = indir / "p1_geographic_aging.csv"
    if not csv_path.exists():
        warnings.warn(f"File not found, skipping Table 3: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    if len(df) == 0:
        warnings.warn("Empty data in p1_geographic_aging.csv, skipping Table 3")
        return None

    # Sort by weighted employment descending, take top 15
    df_sorted = df.sort_values("weighted_n", ascending=False).head(15).copy()
    # Re-sort alphabetically by state for presentation
    df_sorted = df_sorted.sort_values("state")

    doc = create_apa_document()

    add_table_title(
        doc, 3,
        "State-Level Age Distribution of Surveyors (Top 15 States by Employment), "
        "ACS 2020\u20132024"
    )

    headers = ["State", "N", "Median Age (SE)", "% 18\u201334", "% 55+", "High Risk"]
    n_rows = len(df_sorted) + 1
    n_cols = len(headers)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.autofit = True

    # Header
    for j, hdr in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
        set_cell_font(table.rows[0].cells[j], hdr, bold=True, alignment=align)

    # Data rows
    for i, (_, row_data) in enumerate(df_sorted.iterrows()):
        r = i + 1
        row = table.rows[r]

        # State name
        set_cell_font(row.cells[0], str(row_data["state"]),
                      alignment=WD_ALIGN_PARAGRAPH.LEFT)

        # N (weighted)
        set_cell_font(row.cells[1], fmt_n(row_data.get("weighted_n")))

        # Median Age (SE)
        med = row_data.get("median_age")
        se = row_data.get("median_age_SE")
        if pd.notna(med):
            age_str = fmt_dec(med, 1)
            se_str = fmt_se(se)
            if se_str:
                age_str += f" {se_str}"
            set_cell_font(row.cells[2], age_str)
        else:
            set_cell_font(row.cells[2], "\u2014")

        # Percentages
        set_cell_font(row.cells[3], fmt_pct(row_data.get("pct_18_34")))
        set_cell_font(row.cells[4], fmt_pct(row_data.get("pct_55plus")))

        # High risk flag
        flag = row_data.get("high_risk_flag")
        if isinstance(flag, (bool, np.bool_)):
            flag_str = "Yes" if flag else "No"
        elif pd.notna(flag):
            flag_str = "Yes" if str(flag).lower() in ("true", "1", "yes") else "No"
        else:
            flag_str = "\u2014"
        set_cell_font(row.cells[5], flag_str)

    finalize_apa_table(table)

    add_table_note(
        doc,
        "Data from the American Community Survey (ACS) 2020\u20132024, 5-year "
        "PUMS via IPUMS USA. Surveyors identified by OCC = 1310. Only the 15 "
        "states with the largest weighted surveyor employment are shown, sorted "
        "alphabetically. States with fewer than 30 unweighted observations are "
        "suppressed for reliability. N = weighted population estimate. Standard "
        "errors in parentheses estimated via Fay\u2019s BRR (k = 0.5, 80 "
        "replicate weights). High Risk = state where 40% or more of the "
        "surveyor workforce is aged 55 and older."
    )

    out_path = outdir / "table3_state_aging.docx"
    doc.save(str(out_path))
    return str(out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Subagent 5A: TABLES_P1 \u2014 APA 7 formatted tables for "
                    "Paper 1 (Workforce Aging and Contraction)"
    )
    parser.add_argument(
        "--indir", default="analysis/p1",
        help="Directory containing Paper 1 analysis CSVs (default: analysis/p1)",
    )
    parser.add_argument(
        "--outdir", default="tables/p1",
        help="Output directory for .docx table files (default: tables/p1)",
    )
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)

    # Validate input directory
    if not indir.exists():
        print(f"WARNING: Input directory does not exist: {indir}")
        print("Run s4a_aging_analysis.py first to produce analysis CSVs.")
        print("Continuing anyway; individual tables will be skipped if files "
              "are missing.\n")

    outdir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("SUBAGENT 5A: TABLES_P1")
    print("APA 7 formatted publication-ready tables for Paper 1")
    print("=" * 65)
    print(f"  Input directory:  {indir.resolve()}")
    print(f"  Output directory: {outdir.resolve()}")
    print()

    # ------------------------------------------------------------------
    # Build tables
    # ------------------------------------------------------------------
    produced = []
    skipped = []

    # Table 1
    print("Building Table 1: Age Distribution by Occupation and Comparison Group...")
    path1 = build_table1(indir, outdir)
    if path1:
        produced.append(("Table 1", path1))
        print(f"  -> Saved: {path1}")
    else:
        skipped.append("Table 1 (p1_age_distribution.csv not found)")
        print("  -> SKIPPED")

    # Table 2
    print("\nBuilding Table 2: Retirement Cliff Indicators...")
    path2 = build_table2(indir, outdir)
    if path2:
        produced.append(("Table 2", path2))
        print(f"  -> Saved: {path2}")
    else:
        skipped.append("Table 2 (p1_retirement_cliff.csv not found)")
        print("  -> SKIPPED")

    # Table 3
    print("\nBuilding Table 3: State-Level Age Distribution...")
    path3 = build_table3(indir, outdir)
    if path3:
        produced.append(("Table 3", path3))
        print(f"  -> Saved: {path3}")
    else:
        skipped.append("Table 3 (p1_geographic_aging.csv not found)")
        print("  -> SKIPPED")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    if produced:
        print(f"  Tables produced: {len(produced)}")
        for label, path in produced:
            size_kb = Path(path).stat().st_size / 1024
            print(f"    {label}: {Path(path).name}  ({size_kb:.1f} KB)")
    else:
        print("  No tables produced.")

    if skipped:
        print(f"\n  Tables skipped: {len(skipped)}")
        for s in skipped:
            print(f"    {s}")

    if not produced:
        print("\n  Ensure s4a_aging_analysis.py has been run to produce "
              "analysis CSVs in the input directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
