# Running the Analysis Pipeline

## Prerequisites

1. Python 3.9+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Getting the Data

1. Create an IPUMS account at https://usa.ipums.org/usa/
2. Follow the instructions in `project/ipums_download_instructions.txt`
3. Download and decompress the extract:
   ```bash
   gunzip usa_00001.csv.gz
   ```
4. Place the CSV in `data/raw/`

## Running Everything

From the project root directory:

```bash
python scripts/run_pipeline.py --ipums data/raw/usa_00001.csv
```

This runs all 8 scripts in order (~15-30 min depending on machine).

## Running Individual Scripts

Each script can be run independently:

```bash
# Step 1: Filter IPUMS to surveying occupations
python scripts/s1_data_ingest.py --input data/raw/usa_00001.csv

# Step 2: Construct analysis variables
python scripts/s2_recode.py

# Step 3: Build workforce benchmarks (reads FULL IPUMS file)
python scripts/s3_benchmark_build.py --ipums data/raw/usa_00001.csv

# Step 3b: Fetch BLS supplemental data
python scripts/s3b_bls_fetch.py

# Step 4a: Paper 1 aging analysis
python scripts/s4a_aging_analysis.py

# Step 4b: Paper 2 demographic composition
python scripts/s4b_disparity_analysis.py

# Step 4c: Paper 2 earnings analysis + regression
python scripts/s4c_earnings_analysis.py

# Step 4d: Paper 2 geographic analysis
python scripts/s4d_geographic_analysis.py
```

## Output Structure

After running, you'll find:

- `data/surveying_filtered.csv` — Surveyor-only extract (~5K-10K rows)
- `data/surveying_recoded.csv` — With all analysis variables
- `data/benchmarks.csv` — Workforce comparison groups
- `analysis/p1/` — Paper 1 aging analysis results
- `analysis/p2/` — Paper 2 disparity/earnings analysis results

## Resuming After Failure

If the pipeline fails partway through:

```bash
python scripts/run_pipeline.py --ipums data/raw/usa_00001.csv --start-from 5
```

This skips scripts 1-4 and starts from script 5 (Paper 1 analysis).
