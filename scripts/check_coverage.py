"""
check_coverage.py
Enforces 85% minimum per-class Apex code coverage.

Reads coverage from --results-dir JSON files written by sf deploy validate
--coverage-formatters json. Falls back to printing dir contents on failure.

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


def debug_dir(results_dir):
    """Print all files found under results_dir to help diagnose structure."""
    print(f"\nDEBUG: Contents of results dir '{results_dir}':")
    for root, dirs, files in os.walk(results_dir):
        for f in files:
            fpath = os.path.join(root, f)
            print(f"  {fpath}")


def try_parse_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def load_coverage(results_dir, class_filter):
    all_json = glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True)

    coverage_map = {}

    for path in all_json:
        data = try_parse_json(path)
        if data is None:
            continue

        # Format 1: SF CLI coverage.json — { "path/ClassName.cls": { "s": { "1": 1, "2": 0 } } }
        # Keys are file paths, values have statement/branch/function maps
        if isinstance(data, dict) and all(
            isinstance(v, dict) and any(k in v for k in ("s", "b", "f", "fnMap", "statementMap"))
            for v in list(data.values())[:3]
        ):
            for file_path, stats in data.items():
                # Extract class name from path like "force-app/main/default/classes/MyClass.cls"
                cls_name = os.path.splitext(os.path.basename(file_path))[0]
                stmts = stats.get("s", {})
                if stmts:
                    covered   = sum(1 for v in stmts.values() if v > 0)
                    uncovered = sum(1 for v in stmts.values() if v == 0)
                    coverage_map[cls_name] = (covered, uncovered)
            if coverage_map:
                break

        # Format 2: coverage-summary.json — { "ClassName": { "lines": { "covered": N, "total": N } } }
        if isinstance(data, dict) and any(
            isinstance(v, dict) and "lines" in v for v in list(data.values())[:3]
        ):
            for cls_name, stats in data.items():
                if cls_name == "total":
                    continue
                lines     = stats.get("lines", {})
                covered   = lines.get("covered", 0)
                total     = lines.get("total", 0)
                coverage_map[cls_name] = (covered, total - covered)
            if coverage_map:
                break

        # Format 3: SF CLI array — [ { "name": "...", "numLinesCovered": N, "numLinesUncovered": N } ]
        records = None
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = (
                data.get("result", {}).get("codecoverage") or
                data.get("codecoverage") or
                data.get("result", {}).get("details", {}).get("runTestResult", {}).get("codeCoverage")
            )
        if records and isinstance(records, list) and len(records) > 0:
            first = records[0]
            if isinstance(first, dict) and ("name" in first or "numLinesCovered" in first):
                for r in records:
                    name      = r.get("name") or r.get("ApexClassOrTrigger", {}).get("Name", "")
                    covered   = int(r.get("numLinesCovered",   r.get("NumLinesCovered",   0)))
                    uncovered = int(r.get("numLinesUncovered", r.get("NumLinesUncovered", 0)))
                    if name:
                        coverage_map[name] = (covered, uncovered)
                if coverage_map:
                    break

    if not coverage_map:
        debug_dir(results_dir)
        # Print first 500 chars of each json file found to help diagnose
        for path in all_json[:3]:
            print(f"\nDEBUG: Preview of {path}:")
            data = try_parse_json(path)
            if data:
                print(str(data)[:500])
        print(f"\nERROR: No coverage data found in results directory: {results_dir}")
        print("Ensure --coverage-formatters json --results-dir was passed to sf project deploy validate")
        sys.exit(2)

    print(f"Coverage data loaded from results dir. {len(coverage_map)} class(es) found.")

    rows = []
    for cls in class_filter:
        if cls in coverage_map:
            covered, uncovered = coverage_map[cls]
            rows.append((cls, covered, uncovered))
        else:
            print(f"WARNING: No coverage record for '{cls}' - treating as 0%")
            rows.append((cls, 0, 1))

    return rows


# ── Argument parsing ──────────────────────────────────────────────────────────
args = sys.argv[1:]

if "--results-dir" not in args or "--classes" not in args:
    print("Usage: python3 check_coverage.py --results-dir <path> --classes <Class1,Class2>")
    sys.exit(2)

rd_idx      = args.index("--results-dir")
results_dir = args[rd_idx + 1]

cls_idx      = args.index("--classes")
class_filter = [c.strip() for c in args[cls_idx + 1].split(",") if c.strip()]

if not class_filter:
    print("ERROR: --classes requires a comma-separated list of Apex class names")
    sys.exit(2)

if not os.path.isdir(results_dir):
    print(f"ERROR: Results directory not found: {results_dir}")
    print("Ensure --coverage-formatters json --results-dir was passed to sf project deploy validate")
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
