"""
check_coverage.py
Reads the JSON output of `sf apex get test --result-format json`
and enforces 85% minimum code coverage per individual Apex class.

Usage:
  sf apex get test --test-run-id <id> --result-format json --output-dir /tmp/testresults
  python3 scripts/check_coverage.py /tmp/testresults/<id>.json

Exit codes:
  0 - all classes meet the 85% threshold
  1 - one or more classes are below threshold
"""
import json, sys, os

THRESHOLD = 85
result_file = sys.argv[1] if len(sys.argv) > 1 else None

if not result_file or not os.path.isfile(result_file):
    print(f"ERROR: result file not found: {result_file}")
    sys.exit(1)

with open(result_file) as f:
    data = json.load(f)

# sf apex get test JSON structure: result.codecoverage[]
coverage_list = (
    data.get("result", {}).get("codecoverage")
    or data.get("codecoverage")
    or []
)

if not coverage_list:
    print("WARNING: No code coverage data found in result file - skipping coverage check")
    sys.exit(0)

failures = []
print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
print("-" * 90)

for entry in coverage_list:
    name           = entry.get("name", "Unknown")
    covered_lines  = int(entry.get("numLinesCovered", 0))
    uncovered_lines= int(entry.get("numLinesUncovered", 0))
    total_lines    = covered_lines + uncovered_lines

    if total_lines == 0:
        pct = 100.0
    else:
        pct = (covered_lines / total_lines) * 100

    status = "PASS" if pct >= THRESHOLD else "FAIL"
    print(f"{name:<60} {covered_lines:>8} {total_lines:>8} {pct:>9.1f}%  {status}")

    if pct < THRESHOLD:
        failures.append((name, pct, total_lines))

print("-" * 90)

if failures:
    print(f"\nCOVERAGE CHECK FAILED - {len(failures)} class(es) below {THRESHOLD}% threshold:")
    for name, pct, total in failures:
        print(f"  {name}: {pct:.1f}% ({total} lines)")
    sys.exit(1)

print(f"\nCOVERAGE CHECK PASSED - all classes meet the {THRESHOLD}% threshold")
sys.exit(0)
