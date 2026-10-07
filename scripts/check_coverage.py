"""
check_coverage.py
Enforces 85% minimum per-class Apex code coverage from sf deploy validate results.

Usage:
  python3 check_coverage.py --results-dir <path> --classes <Class1,Class2,...>

Exit codes:
  0 - all classes meet 85% threshold
  1 - one or more classes below threshold
  2 - input / data error
"""
import json, sys, os, glob

THRESHOLD = 85


def calc_pct(covered, uncovered):
    total = covered + uncovered
    return 100.0 if total == 0 else (covered / total) * 100


def print_table(rows):
    failures = []
    print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
    print("-" * 92)
    for name, covered, uncovered in rows:
        pct    = calc_pct(covered, uncovered)
        status = "PASS" if pct >= THRESHOLD else "FAIL"
        print(f"{name:<60} {covered:>8} {covered+uncovered:>8} {pct:>9.1f}%  {status}")
        if pct < THRESHOLD:
            failures.append((name, pct, covered + uncovered))
    print("-" * 92)
    return failures


def load_coverage(results_dir, class_filter):
    """
    Reads coverage from sf deploy validate --coverage-formatters json output.
    Looks for coverage-summary.json or any .json file under results_dir.
    """
    # Try coverage-summary.json first, then any json file
    candidates = (
        glob.glob(os.path.join(results_dir, "**", "coverage-summary.json"), recursive=True) +
        glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True)
    )
    candidates = list(dict.fromkeys(candidates))  # deduplicate, preserve order

    coverage_map = {}
    for path in candidates:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        # istanbul/v8 coverage-summary.json format: { "ClassName": { "lines": { "covered": N, "total": N } } }
        if isinstance(data, dict) and any(isinstance(v, dict) and "lines" in v for v in data.values()):
            for cls_name, stats in data.items():
                if cls_name == "total":
                    continue
                lines = stats.get("lines", {})
                covered   = lines.get("covered", 0)
                total     = lines.get("total", 0)
                uncovered = total - covered
                coverage_map[cls_name] = (covered, uncovered)
            if coverage_map:
                break

        # sf CLI codecoverage array format: [ { "name": "...", "numLinesCovered": N, "numLinesUncovered": N } ]
        records = None
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = (
                data.get("result", {}).get("codecoverage") or
                data.get("codecoverage") or
                data.get("result", {}).get("details", {}).get("runTestResult", {}).get("codeCoverage")
            )
        if records and isinstance(records, list):
            for r in records:
                name      = r.get("name") or r.get("ApexClassOrTrigger", {}).get("Name", "")
                covered   = int(r.get("numLinesCovered",   r.get("NumLinesCovered",   0)))
                uncovered = int(r.get("numLinesUncovered", r.get("NumLinesUncovered", 0)))
                if name:
                    coverage_map[name] = (covered, uncovered)
            if coverage_map:
                break

    if not coverage_map:
        print(f"ERROR: No coverage data found in results directory: {results_dir}")
        print("Ensure --coverage-formatters json --results-dir was passed to sf project deploy validate")
        sys.exit(2)

    # Filter to requested classes only
    rows = []
    missing = []
    for cls in class_filter:
        if cls in coverage_map:
            covered, uncovered = coverage_map[cls]
            rows.append((cls, covered, uncovered))
        else:
            print(f"WARNING: No coverage record for '{cls}' - treating as 0%")
            rows.append((cls, 0, 1))
            missing.append(cls)

    return rows


# ── Argument parsing ──────────────────────────────────────────────────────────
args = sys.argv[1:]

if "--results-dir" not in args or "--classes" not in args:
    print("Usage: python3 check_coverage.py --results-dir <path> --classes <Class1,Class2>")
    sys.exit(2)

rd_idx = args.index("--results-dir")
results_dir = args[rd_idx + 1]

cls_idx = args.index("--classes")
class_filter = [c.strip() for c in args[cls_idx + 1].split(",") if c.strip()]

if not class_filter:
    print("ERROR: --classes requires a comma-separated list of Apex class names")
    sys.exit(2)

if not os.path.isdir(results_dir):
    print(f"ERROR: Results directory not found: {results_dir}")
    sys.exit(2)

# ── Run ───────────────────────────────────────────────────────────────────────
rows = load_coverage(results_dir, class_filter)
print(f"Checking {len(rows)} class(es) against {THRESHOLD}% threshold...")
failures = print_table(rows)

if failures:
    print(f"\nCOVERAGE CHECK FAILED - {len(failures)} class(es) below {THRESHOLD}%:")
    for name, pct, total in failures:
        print(f"  {name}: {pct:.1f}% ({total} lines)")
    sys.exit(1)

print(f"\nCOVERAGE CHECK PASSED - all {len(rows)} class(es) meet {THRESHOLD}%")
sys.exit(0)
