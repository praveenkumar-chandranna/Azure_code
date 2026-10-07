"""
check_coverage.py
Enforces 85% minimum code coverage per individual Apex class.

Usage:
  python3 check_coverage.py --soql <sf-username-or-alias> --classes <Class1,Class2,...>

Exit codes:
  0 - all classes meet the 85% threshold
  1 - one or more classes are below threshold
  2 - input error / no data found
"""
import json, sys, os, subprocess

THRESHOLD = 85


def calc_pct(covered, uncovered):
    total = covered + uncovered
    return 100.0 if total == 0 else (covered / total) * 100


def print_table(coverage_list):
    failures = []
    print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
    print("-" * 92)
    for entry in coverage_list:
        name      = entry.get("name", "Unknown")
        covered   = int(entry.get("numLinesCovered", 0))
        uncovered = int(entry.get("numLinesUncovered", 0))
        pct       = calc_pct(covered, uncovered)
        status    = "PASS" if pct >= THRESHOLD else "FAIL"
        print(f"{name:<60} {covered:>8} {covered+uncovered:>8} {pct:>9.1f}%  {status}")
        if pct < THRESHOLD:
            failures.append((name, pct, covered + uncovered))
    print("-" * 92)
    return failures


def load_coverage_from_soql(username, class_filter):
    """Query ApexCodeCoverageAggregate for specific classes only."""
    names_in = ", ".join(f"'{c.strip()}'" for c in class_filter)
    query = (
        f"SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered "
        f"FROM ApexCodeCoverageAggregate "
        f"WHERE ApexClassOrTrigger.Name IN ({names_in}) "
        f"ORDER BY ApexClassOrTrigger.Name"
    )
    cmd = [
        "sf", "data", "query",
        "--query", query,
        "--target-org", username,
        "--result-format", "json",
        "--use-tooling-api"
    ]
    print(f"Querying coverage from org '{username}' for {len(class_filter)} class(es)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: SOQL query failed:\n{result.stderr}")
        sys.exit(2)

    data = json.loads(result.stdout)
    records = data.get("result", {}).get("records", [])

    if not records:
        print(f"ERROR: No coverage records found in org for classes: {class_filter}")
        print("Ensure tests were executed and coverage data exists in the org.")
        sys.exit(2)

    # Warn about classes with no coverage record at all
    found_names = {r.get("ApexClassOrTrigger", {}).get("Name", "") for r in records}
    missing = [c for c in class_filter if c.strip() not in found_names]
    if missing:
        print(f"WARNING: No coverage record found for: {missing}")
        print("These classes will be treated as 0% coverage.")
        for m in missing:
            records.append({
                "ApexClassOrTrigger": {"Name": m.strip()},
                "NumLinesCovered": 0,
                "NumLinesUncovered": 1
            })

    return [
        {
            "name":             r.get("ApexClassOrTrigger", {}).get("Name", "Unknown"),
            "numLinesCovered":  r.get("NumLinesCovered", 0),
            "numLinesUncovered":r.get("NumLinesUncovered", 0),
        }
        for r in records
    ]


# ── Argument parsing ──────────────────────────────────────────────────────────
args = sys.argv[1:]

if "--soql" not in args:
    print("Usage: python3 check_coverage.py --soql <username> --classes <Class1,Class2>")
    sys.exit(2)

soql_idx = args.index("--soql")
if soql_idx + 1 >= len(args):
    print("ERROR: --soql requires a username/alias argument")
    sys.exit(2)
username = args[soql_idx + 1]

class_filter = []
if "--classes" in args:
    cls_idx = args.index("--classes")
    if cls_idx + 1 >= len(args):
        print("ERROR: --classes requires a comma-separated list of class names")
        sys.exit(2)
    class_filter = [c.strip() for c in args[cls_idx + 1].split(",") if c.strip()]

if not class_filter:
    print("ERROR: --classes is required - provide comma-separated Apex class names from the delta package")
    sys.exit(2)

# ── Run coverage check ────────────────────────────────────────────────────────
coverage_list = load_coverage_from_soql(username, class_filter)

print(f"Checking {len(coverage_list)} class(es) against {THRESHOLD}% threshold...")
failures = print_table(coverage_list)

if failures:
    print(f"\nCOVERAGE CHECK FAILED - {len(failures)} class(es) below {THRESHOLD}%:")
    for name, pct, total in failures:
        print(f"  {name}: {pct:.1f}% ({total} lines)")
    sys.exit(1)

print(f"\nCOVERAGE CHECK PASSED - all {len(coverage_list)} class(es) meet {THRESHOLD}%")
sys.exit(0)

import json, sys, os, subprocess

THRESHOLD = 85


def calc_pct(covered, uncovered):
    total = covered + uncovered
    return 100.0 if total == 0 else (covered / total) * 100


def print_table(coverage_list):
    failures = []
    print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
    print("-" * 92)
    for entry in coverage_list:
        name     = entry.get("name") or entry.get("ApexClassOrTrigger", {}).get("Name", "Unknown")
        covered  = int(entry.get("numLinesCovered",   entry.get("NumLinesCovered",   0)))
        uncovered= int(entry.get("numLinesUncovered", entry.get("NumLinesUncovered", 0)))
        pct      = calc_pct(covered, uncovered)
        status   = "PASS" if pct >= THRESHOLD else "FAIL"
        print(f"{name:<60} {covered:>8} {covered+uncovered:>8} {pct:>9.1f}%  {status}")
        if pct < THRESHOLD:
            failures.append((name, pct, covered + uncovered))
    print("-" * 92)
    return failures


def load_coverage_from_file(path):
    """Try every known SF CLI JSON structure to extract codecoverage list."""
    with open(path) as f:
        data = json.load(f)

    # Structure 1: { "result": { "codecoverage": [...] } }
    cov = data.get("result", {}).get("codecoverage")
    if cov:
        return cov

    # Structure 2: { "codecoverage": [...] }
    cov = data.get("codecoverage")
    if cov:
        return cov

    # Structure 3: { "result": { "details": { "runTestResult": { "codeCoverage": [...] } } } }
    cov = (data.get("result", {})
               .get("details", {})
               .get("runTestResult", {})
               .get("codeCoverage"))
    if cov:
        return cov

    # Structure 4: top-level list
    if isinstance(data, list):
        return data

    # Structure 5: { "result": [ ... ] }  (some CLI versions)
    cov = data.get("result")
    if isinstance(cov, list):
        return cov

    return None


def load_coverage_from_soql(username):
    """Query ApexCodeCoverageAggregate via SF CLI SOQL."""
    query = (
        "SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered "
        "FROM ApexCodeCoverageAggregate "
        "ORDER BY ApexClassOrTrigger.Name"
    )
    cmd = [
        "sf", "data", "query",
        "--query", query,
        "--target-org", username,
        "--result-format", "json",
        "--use-tooling-api"
    ]
    print(f"Querying coverage from org: {username}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: SOQL query failed:\n{result.stderr}")
        sys.exit(2)

    data = json.loads(result.stdout)
    records = data.get("result", {}).get("records", [])
    if not records:
        print("ERROR: No coverage records returned from org SOQL query")
        sys.exit(2)

    # Normalise to same shape as file-based coverage
    normalised = []
    for r in records:
        normalised.append({
            "name": r.get("ApexClassOrTrigger", {}).get("Name", "Unknown"),
            "numLinesCovered":   r.get("NumLinesCovered", 0),
            "numLinesUncovered": r.get("NumLinesUncovered", 0),
        })
    return normalised


# ── Entry point ───────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Usage:")
    print("  python3 check_coverage.py <result.json>")
    print("  python3 check_coverage.py --soql <sf-username>")
    sys.exit(2)

if sys.argv[1] == "--soql":
    if len(sys.argv) < 3:
        print("ERROR: --soql requires a Salesforce username/alias argument")
        sys.exit(2)
    coverage_list = load_coverage_from_soql(sys.argv[2])
else:
    result_file = sys.argv[1]
    if not os.path.isfile(result_file):
        print(f"ERROR: Result file not found: {result_file}")
        print("Coverage check cannot be bypassed - failing the pipeline.")
        sys.exit(2)

    coverage_list = load_coverage_from_file(result_file)

    if not coverage_list:
        print(f"ERROR: No coverage data found in: {result_file}")
        print("File contents preview:")
        with open(result_file) as f:
            print(f.read()[:500])
        print("\nCoverage check cannot be bypassed - failing the pipeline.")
        sys.exit(2)

print(f"Checking {len(coverage_list)} class(es) against {THRESHOLD}% threshold...")
failures = print_table(coverage_list)

if failures:
    print(f"\nCOVERAGE CHECK FAILED - {len(failures)} class(es) below {THRESHOLD}%:")
    for name, pct, total in failures:
        print(f"  {name}: {pct:.1f}% ({total} lines)")
    sys.exit(1)

print(f"\nCOVERAGE CHECK PASSED - all {len(coverage_list)} class(es) meet {THRESHOLD}%")
sys.exit(0)
