"""
check_coverage.py
Enforces 85% minimum per-class Apex code coverage.

Two modes:
  --mode local  : reads coverage from --results-dir JSON files written by
                  sf project deploy start --coverage-formatters json
  --mode org    : queries coverage directly from Salesforce org via sf data query

Usage:
  python3 check_coverage.py --mode local  --results-dir <path> --classes <Class1,Class2>
  python3 check_coverage.py --mode org    --username <user>     --classes <Class1,Class2>

Exit codes:
  0 - all classes meet 85% threshold
  1 - one or more classes below threshold
  2 - input / data error
"""
import json, sys, os, glob, subprocess

THRESHOLD = 85


def calc_pct(covered, uncovered):
    total = covered + uncovered
    if total == 0:
        return None
    return (covered / total) * 100


def print_table(rows):
    failures = []
    print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
    print("-" * 92)
    for name, covered, uncovered in rows:
        pct = calc_pct(covered, uncovered)
        if pct is None:
            print(f"{name:<60} {'N/A':>8} {'N/A':>8} {'NO DATA':>10}  FAIL")
            failures.append((name, 0.0, 0))
        else:
            status = "PASS" if pct >= THRESHOLD else "FAIL"
            print(f"{name:<60} {covered:>8} {covered+uncovered:>8} {pct:>9.1f}%  {status}")
            if pct < THRESHOLD:
                failures.append((name, pct, covered + uncovered))
    print("-" * 92)
    return failures


# ── Mode: org (SOQL query via SF CLI) ────────────────────────────────────────
def load_coverage_from_org(username, class_filter):
    print(f"Querying Apex code coverage from org: {username}")
    names_in = ", ".join(f"'{c}'" for c in class_filter)
    # First get only non-test Apex class names from the filter list
    apex_query = (
        f"SELECT Name FROM ApexClass "
        f"WHERE Name IN ({names_in}) AND IsTest = false"
    )
    apex_result = subprocess.run(
        ["sf", "data", "query", "--query", apex_query, "--target-org", username, "--json"],
        capture_output=True, text=True
    )
    try:
        apex_data = json.loads(apex_result.stdout)
        apex_records = apex_data.get("result", {}).get("records", [])
        apex_classes = {r["Name"].lower() for r in apex_records if r.get("Name")}
    except Exception:
        apex_classes = None

    # Filter class_filter to only non-test classes
    if apex_classes:
        filtered = [c for c in class_filter if c.lower() in apex_classes]
        skipped  = [c for c in class_filter if c.lower() not in apex_classes]
        if skipped:
            print(f"INFO: Skipping test classes (not subject to coverage): {skipped}")
        class_filter = filtered if filtered else class_filter
        names_in = ", ".join(f"'{c}'" for c in class_filter)

    query = (
        f"SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered "
        f"FROM ApexCodeCoverageAggregate "
        f"WHERE ApexClassOrTrigger.Name IN ({names_in})"
    )
    result = subprocess.run(
        ["sf", "data", "query", "--query", query, "--target-org", username, "--use-tooling-api", "--json"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
    except Exception:
        print(f"ERROR: Could not parse SF CLI output:\n{result.stdout}\n{result.stderr}")
        sys.exit(2)

    if data.get("status") != 0:
        print(f"ERROR: SOQL query failed: {data.get('message', result.stderr)}")
        sys.exit(2)

    records = data.get("result", {}).get("records", [])
    print(f"Coverage records returned from org: {len(records)}")
    for r in records:
        name = r.get("ApexClassOrTrigger", {}).get("Name", "")
        print(f"  {name} covered={r.get('NumLinesCovered',0)} uncovered={r.get('NumLinesUncovered',0)}")

    coverage_map = {}
    for r in records:
        name      = r.get("ApexClassOrTrigger", {}).get("Name", "")
        covered   = int(r.get("NumLinesCovered",   0))
        uncovered = int(r.get("NumLinesUncovered", 0))
        if name:
            coverage_map[name.lower()] = (name, covered, uncovered)

    rows, missing = [], []
    for cls in class_filter:
        match = coverage_map.get(cls.lower())
        if match:
            org_name, covered, uncovered = match
            if org_name != cls:
                print(f"INFO: Case-insensitive match '{cls}' -> '{org_name}'")
            rows.append((cls, covered, uncovered))
        else:
            missing.append(cls)
            print(f"WARNING: No coverage record for '{cls}' in org")

    if missing:
        print(f"\nERROR: {len(missing)} class(es) have no coverage data in org: {missing}")
        print("Ensure test classes covering these classes have been run in the org.")
        sys.exit(2)
    return rows


# ── Extract coverage from a single JSON file (all known SF CLI formats) ───────
def extract_coverage_from_json(data, path):
    """Returns {className: (covered, uncovered)} or {} if no match."""
    tmp = {}
    fname = os.path.basename(path)

    # Resolve records list from all known SF CLI output locations
    records = None
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = (
            data.get("result", {}).get("codecoverage") or
            data.get("codecoverage") or
            data.get("coverage", {}).get("coverage") or
            data.get("result", {}).get("details", {}).get("runTestResult", {}).get("codeCoverage")
        )

    # Format 1a: SF CLI deploy JSON — records with numLinesCovered / numLinesUncovered
    # Format 1b: SF CLI test JSON  — records with coveredLines / uncoveredLines as lists
    # Format 1c: records with lines.covered / lines.total
    if records and isinstance(records, list):
        for r in records:
            if not isinstance(r, dict):
                continue
            name = r.get("name") or r.get("ApexClassOrTrigger", {}).get("Name", "")
            if not name:
                continue
            if "numLinesCovered" in r or "NumLinesCovered" in r:
                covered   = int(r.get("numLinesCovered",   r.get("NumLinesCovered",   0)))
                uncovered = int(r.get("numLinesUncovered", r.get("NumLinesUncovered", 0)))
                tmp[name] = (covered, uncovered)
            elif "coveredLines" in r or "uncoveredLines" in r:
                covered   = len(r.get("coveredLines",   []) or [])
                uncovered = len(r.get("uncoveredLines", []) or [])
                tmp[name] = (covered, uncovered)
            elif "lines" in r and isinstance(r.get("lines"), dict):
                lines     = r["lines"]
                covered   = int(lines.get("covered", 0))
                total     = int(lines.get("total",   0))
                tmp[name] = (covered, total - covered)
        if tmp:
            print(f"  Matched Format 1 (SF CLI records) in {fname} - {len(tmp)} classes")
            return tmp

    # Format 2: coverage-summary.json — {"ClassName": {"lines": {"covered": N, "total": N}}}
    if isinstance(data, dict):
        for cls_name, stats in data.items():
            if not isinstance(stats, dict) or cls_name == "total":
                continue
            if "lines" in stats and isinstance(stats["lines"], dict):
                lines     = stats["lines"]
                covered   = int(lines.get("covered", 0))
                total     = int(lines.get("total",   0))
                tmp[cls_name] = (covered, total - covered)
        if tmp:
            print(f"  Matched Format 2 (coverage-summary) in {fname} - {len(tmp)} classes")
            return tmp

    # Format 3: Istanbul — {"path/ClassName.cls": {"s": {}, "l": {"1": 1, "2": 0}}}
    if isinstance(data, dict):
        for file_path, stats in data.items():
            if not isinstance(stats, dict):
                continue
            if not any(k in stats for k in ("s", "l", "fnMap", "statementMap")):
                continue
            cls_name = os.path.splitext(os.path.basename(file_path))[0]
            # Prefer "l" (line coverage) over "s" (statement coverage) — more reliable
            counts = stats.get("l") or stats.get("s") or {}
            if counts:
                covered   = sum(1 for v in counts.values() if v > 0)
                uncovered = sum(1 for v in counts.values() if v == 0)
                tmp[cls_name] = (covered, uncovered)
                print(f"    Istanbul: {cls_name} covered={covered} uncovered={uncovered} total={covered+uncovered}")
        if tmp:
            print(f"  Matched Format 3 (Istanbul) in {fname} - {len(tmp)} classes")
            return tmp

    return {}


# ── Mode: local (reads JSON from results-dir) ─────────────────────────────────
def load_coverage_from_local(results_dir, class_filter):
    all_json = glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True)
    print(f"\nFound {len(all_json)} JSON file(s) in results dir:")
    for p in all_json:
        print(f"  {p}")

    # Scan ALL json files — pick best (highest total lines) result per class
    coverage_map = {}
    for path in all_json:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"WARNING: Skipping {path} - JSON parse error: {e}")
            continue
        extracted = extract_coverage_from_json(data, path)
        for name, (cov, uncov) in extracted.items():
            existing = coverage_map.get(name)
            # Keep the record with the most lines (most complete coverage data)
            if existing is None or (cov + uncov) > (existing[0] + existing[1]):
                coverage_map[name] = (cov, uncov)

    if not coverage_map:
        print(f"\nERROR: No coverage data found in results directory: {results_dir}")
        print("Ensure --coverage-formatters json --results-dir was passed to sf project deploy start")
        sys.exit(2)

    print(f"Coverage data loaded. {len(coverage_map)} class(es) found.")
    rows = []
    for name, (covered, uncovered) in coverage_map.items():
        cls_name = os.path.splitext(os.path.basename(name))[0]
        print(f"  -> {cls_name}: covered={covered} uncovered={uncovered}")
        rows.append((cls_name, covered, uncovered))
    return rows


# ── Argument parsing ──────────────────────────────────────────────────────────
args = sys.argv[1:]

# --skip-check: bypass coverage enforcement (e.g. validation/PR pipelines)
if "--skip-check" in args:
    print("Coverage check skipped (--skip-check flag set).")
    sys.exit(0)

mode = "org"
if "--mode" in args:
    mode = args[args.index("--mode") + 1]

if "--classes" not in args:
    print("Usage: python3 check_coverage.py --username <user> --classes <Class1,Class2>")
    print("       python3 check_coverage.py --mode local --results-dir <path> --classes <Class1,Class2>")
    print("       python3 check_coverage.py --skip-check")
    sys.exit(2)

cls_idx      = args.index("--classes")
class_filter = [c.strip() for c in args[cls_idx + 1].split(",") if c.strip()]

if not class_filter:
    print("ERROR: --classes requires a comma-separated list of Apex class names")
    sys.exit(2)

# ── Run ───────────────────────────────────────────────────────────────────────
if mode == "org":
    if "--username" not in args:
        print("ERROR: --mode org requires --username <sf_username>")
        sys.exit(2)
    username = args[args.index("--username") + 1]
    rows = load_coverage_from_org(username, class_filter)
else:
    if "--results-dir" not in args:
        print("ERROR: --mode local requires --results-dir <path>")
        sys.exit(2)
    results_dir = args[args.index("--results-dir") + 1]
    if not os.path.isdir(results_dir):
        print(f"ERROR: Results directory not found: {results_dir}")
        sys.exit(2)
    rows = load_coverage_from_local(results_dir, class_filter)

print(f"Checking {len(rows)} class(es) against {THRESHOLD}% threshold...")
failures = print_table(rows)

if failures:
    print(f"\nCOVERAGE CHECK FAILED - {len(failures)} class(es) below {THRESHOLD}%:")
    for name, pct, total in failures:
        if total == 0:
            print(f"  {name}: NO DATA (no test coverage recorded)")
        else:
            print(f"  {name}: {pct:.1f}% ({total} lines)")
    sys.exit(1)

print(f"\nCOVERAGE CHECK PASSED - all {len(rows)} class(es) meet {THRESHOLD}%")
sys.exit(0)
