# CLAUDE.md — Surveying Workforce Research Series

## Project Overview

Three-paper academic research series analyzing the U.S. surveying/geospatial workforce using IPUMS American Community Survey (ACS) microdata. Author: Jose A. Pedraza, RPLS, PLS, PMP (Pedraza Surveying, LLC / Lone Star College adjunct faculty).

**Papers:**
- **Paper 1** — Workforce aging and retirement cliff analysis
- **Paper 2** — Demographic disparity (race/ethnicity, gender) framed as both an equity problem and a supply constraint; includes earnings gap regression (OLS), self-employment rates, and brief international comparison (UK/Australia)
- **Paper 3** — Pipeline solutions (Klein Collins HS geospatial program, DoD SkillBridge/MOS 12T, architecture NCARB model); peer-reviewed version stays academic, separate trade adaptation for practitioner audience

## Data

- **Primary extract:** ACS 2020-2024 5-year (IPUMS USA). ~15-16M rows, ~5-8 GB uncompressed. Too large for git — stored locally in `data/raw/` (gitignored).
- **Trend extract:** ACS 1-year samples (2010, 2015, 2019, 2021-2024) for Paper 1 aging trends.
- **Surveying occupation:** OCC code **1310** (NOT 1530). This was a critical fix — always verify OCC filtering uses 1310.
- **Replicate weights:** REPWTP1-REPWTP80 are required for standard error estimation. Halt if missing.
- IPUMS citation is **mandatory** in every paper — see `project/citations_required.txt`.

## Analysis Pipeline

Run everything: `python scripts/run_pipeline.py --ipums data/raw/usa_00001.csv`

Individual scripts in order:

| # | Script | Purpose |
|---|--------|---------|
| 1 | `s1_data_ingest.py` | Filter IPUMS to surveying occupations (OCC=1310) |
| 2 | `s2_recode.py` | Construct analysis variables (age groups, race/ethnicity, education, CPI-adjusted earnings) |
| 3 | `s3_benchmark_build.py` | Build comparison workforce benchmarks (reads full IPUMS file) |
| 4 | `s3b_bls_fetch.py` | Fetch BLS OEWS and projections data |
| 5 | `s4a_aging_analysis.py` | Paper 1: age distribution, retirement cliff, geographic aging |
| 6 | `s4b_disparity_analysis.py` | Paper 2: demographic composition, representation ratios |
| 7 | `s4c_earnings_analysis.py` | Paper 2: earnings gaps, OLS wage regression |
| 8 | `s4d_geographic_analysis.py` | Paper 2: state-level demographic patterns |
| 9 | `s5a_tables_p1.py` | Paper 1: APA 7 formatted tables (.docx) |
| 10 | `s5b_tables_p2.py` | Paper 2: APA 7 formatted tables (.docx) |
| 11 | `s6a_figures_p1.py` | Paper 1: publication-quality figures (.png/.pdf) |
| 12 | `s6b_figures_p2.py` | Paper 2: publication-quality figures (.png/.pdf) |

Resume after failure: `python scripts/run_pipeline.py --ipums data/raw/usa_00001.csv --start-from 5`

## Key Technical Notes

- **numpy 2.x compatibility:** Use `pd.isna()` instead of `np.isna()` — this was a prior bug fix.
- **CLASSWKR recode:** Was fixed for argument mismatch — check carefully if modifying `s2_recode.py`.
- **CPI deflators:** Adjusted to 2024 dollars (updated when switching to ACS 2020-2024).
- **Colorblind-safe palettes:** Figures use accessible color schemes — maintain this in any new visualizations.
- **Weighted statistics:** All population estimates must use PERWT. Standard errors use successive-difference replication (REPWTP). Never report unweighted counts as estimates.

## Directory Structure

```
literature/       — Literature scan results, gap analyses (completed)
project/          — Session notes, scope log, IPUMS instructions, citations
scripts/          — Python analysis pipeline (12 scripts + runner)
data/raw/         — IPUMS extracts (gitignored, user must download)
data/             — Intermediate filtered/recoded data (gitignored)
analysis/p1/      — Paper 1 analysis outputs (gitignored)
analysis/p2/      — Paper 2 analysis outputs (gitignored)
tables/           — APA 7 formatted .docx tables (gitignored)
figures/          — Publication figures (gitignored)
```

## Scope Decisions

All scope changes are tracked in `project/scope_log.txt`. Key decisions:
- Disability analysis was **declined** (keep extract simpler)
- NSPS demographic reporting gap is framed as a research finding, not just a limitation
- Architecture (NCARB) is the primary comparison profession
- Proactive suggestions are welcome — log proposals in scope_log.txt with user decisions

## Dependencies

```bash
pip install -r requirements.txt
```

Python 3.9+. Key packages: pandas, numpy, scipy, statsmodels, matplotlib, seaborn, python-docx, openpyxl.
