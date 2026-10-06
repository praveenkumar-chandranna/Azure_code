"""
check_coverage.py
Enforces 85% minimum code coverage per individual Apex class.

Supports two input modes:
  1. File mode  : python3 check_coverage.py <path-to-json>
  2. SOQL mode  : python3 check_coverage.py --soql <sf-username>
                  Queries ApexCodeCoverageAggregate directly from the org.

Exit codes:
  0 - all classes meet the 85% threshold
  1 - one or more classes are below threshold
  2 - input error / no data found (treated as failure, not a bypass)
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
