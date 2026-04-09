"""
Master Pipeline Runner
=======================
Runs all analysis scripts in order for the Surveying Workforce Research Series.

Usage:
    python scripts/run_pipeline.py --ipums data/raw/usa_00001.csv

This will run:
    1. s1_data_ingest.py    — Filter IPUMS to surveying occupations
    2. s2_recode.py         — Construct analysis variables
    3. s3_benchmark_build.py — Build workforce benchmarks
    4. s3b_bls_fetch.py     — Fetch BLS supplemental data
    5. s4a_aging_analysis.py — Paper 1: aging/retirement cliff
    6. s4b_disparity_analysis.py — Paper 2: demographic composition
    7. s4c_earnings_analysis.py  — Paper 2: earnings gaps + regression
    8. s4d_geographic_analysis.py — Paper 2: state-level demographics

Each script can also be run individually. See --help on each for options.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


SCRIPTS = [
    {
        "name": "S1: DATA_INGEST",
        "script": "scripts/s1_data_ingest.py",
        "args_template": "--input {ipums} --output data/surveying_filtered.csv",
        "needs_ipums": True,
    },
    {
        "name": "S2: RECODE",
        "script": "scripts/s2_recode.py",
        "args_template": "--input data/surveying_filtered.csv --output data/surveying_recoded.csv",
        "needs_ipums": False,
    },
    {
        "name": "S3: BENCHMARK_BUILD",
        "script": "scripts/s3_benchmark_build.py",
        "args_template": "--ipums {ipums} --output data/benchmarks.csv",
        "needs_ipums": True,
    },
    {
        "name": "S3B: BLS_FETCH",
        "script": "scripts/s3b_bls_fetch.py",
        "args_template": "--output-dir data/supplemental/",
        "needs_ipums": False,
    },
    {
        "name": "S4A: AGING_ANALYSIS (Paper 1)",
        "script": "scripts/s4a_aging_analysis.py",
        "args_template": "--input data/surveying_recoded.csv --benchmarks data/benchmarks.csv --outdir analysis/p1/",
        "needs_ipums": False,
    },
    {
        "name": "S4B: DISPARITY_ANALYSIS (Paper 2)",
        "script": "scripts/s4b_disparity_analysis.py",
        "args_template": "--input data/surveying_recoded.csv --benchmarks data/benchmarks.csv --outdir analysis/p2/",
        "needs_ipums": False,
    },
    {
        "name": "S4C: EARNINGS_ANALYSIS (Paper 2)",
        "script": "scripts/s4c_earnings_analysis.py",
        "args_template": "--input data/surveying_recoded.csv --outdir analysis/p2/",
        "needs_ipums": False,
    },
    {
        "name": "S4D: GEOGRAPHIC_ANALYSIS (Paper 2)",
        "script": "scripts/s4d_geographic_analysis.py",
        "args_template": "--input data/surveying_recoded.csv --outdir analysis/p2/",
        "needs_ipums": False,
    },
]


def run_script(name, script, args_str):
    """Run a single script and return success/failure."""
    cmd = [sys.executable, script] + args_str.split()
    print(f"\n{'='*60}")
    print(f"RUNNING: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    start = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"\n  {name} completed in {elapsed:.1f}s")
        return True
    else:
        print(f"\n  *** {name} FAILED (exit code {result.returncode}) after {elapsed:.1f}s")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Master Pipeline Runner — Surveying Workforce Research Series"
    )
    parser.add_argument("--ipums", required=True,
                        help="Path to FULL IPUMS extract (CSV)")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Start from script number (1-8). Useful for resuming.")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="Stop pipeline if any script fails")
    args = parser.parse_args()

    ipums_path = Path(args.ipums)
    if not ipums_path.exists():
        print(f"ERROR: IPUMS file not found: {ipums_path}")
        sys.exit(1)

    print("=" * 60)
    print("SURVEYING WORKFORCE RESEARCH SERIES")
    print("Master Pipeline Runner")
    print("=" * 60)
    print(f"\nIPUMS extract: {ipums_path}")
    print(f"Starting from script: {args.start_from}")
    print(f"Total scripts: {len(SCRIPTS)}")

    results = {}
    overall_start = time.time()

    for i, script_info in enumerate(SCRIPTS, 1):
        if i < args.start_from:
            print(f"\n  Skipping {script_info['name']} (start-from={args.start_from})")
            continue

        # Build args string
        args_str = script_info["args_template"]
        if script_info["needs_ipums"]:
            args_str = args_str.format(ipums=str(ipums_path))

        # Check script exists
        if not Path(script_info["script"]).exists():
            print(f"\n  WARNING: Script not found: {script_info['script']}. Skipping.")
            results[script_info["name"]] = "SKIPPED"
            continue

        success = run_script(script_info["name"], script_info["script"], args_str)
        results[script_info["name"]] = "OK" if success else "FAILED"

        if not success and args.stop_on_error:
            print(f"\n  Stopping pipeline due to --stop-on-error flag.")
            break

    # Summary
    total_time = time.time() - overall_start
    print(f"\n\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    for name, status in results.items():
        marker = "  " if status == "OK" else "**"
        print(f"  {marker} {name}: {status}")
    print(f"\nTotal time: {total_time:.1f}s ({total_time/60:.1f} min)")

    # Check outputs
    expected_files = [
        "data/surveying_filtered.csv",
        "data/surveying_recoded.csv",
        "data/benchmarks.csv",
        "data/supplemental/bls_oews_surveyors.csv",
        "data/supplemental/bls_projections.csv",
        "analysis/p1/p1_age_distribution.csv",
        "analysis/p1/p1_retirement_cliff.csv",
        "analysis/p1/p1_geographic_aging.csv",
        "analysis/p2/p2_composition.csv",
        "analysis/p2/p2_representation_ratios.csv",
        "analysis/p2/p2_earnings_core.csv",
        "analysis/p2/p2_wage_gaps.csv",
        "analysis/p2/p2_wage_regression.csv",
        "analysis/p2/p2_state_composition.csv",
    ]

    print(f"\nOutput files:")
    for f in expected_files:
        exists = Path(f).exists()
        status = "EXISTS" if exists else "MISSING"
        print(f"  {'  ' if exists else '**'} {f}: {status}")

    failed = [k for k, v in results.items() if v == "FAILED"]
    if failed:
        print(f"\n  {len(failed)} script(s) failed. Review output above for details.")
        sys.exit(1)
    else:
        print(f"\n  All scripts completed successfully.")


if __name__ == "__main__":
    main()
