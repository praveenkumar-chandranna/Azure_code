"""
org_coverage_report.py
Queries ApexCodeCoverageAggregate + ApexTestResult from a Salesforce org via
Tooling API, enforces 85% threshold, generates Excel report + markdown summary.

Exit codes:
  0 - all classes meet threshold
  1 - one or more classes below threshold
  2 - data / query error
"""

import json, sys, os, subprocess, argparse, shutil, re, html, logging
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

THRESHOLD  = 85
CHUNK_SIZE = 100

# Allowed characters for env/timestamp args to prevent path traversal
_SAFE_ARG = re.compile(r'^[A-Za-z0-9_\-\.]+$')


def _safe_arg(value, name):
    """Reject CLI arg values containing path traversal or shell-unsafe characters."""
    if not _SAFE_ARG.match(str(value)):
        logging.error("Invalid value for --%s: %r", name, value)
        sys.exit(2)
    return value


def _safe_output_dir(path):
    """Resolve output_dir and ensure it is an existing absolute directory."""
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        logging.error("--output-dir does not exist or is not a directory: %s", resolved)
        sys.exit(2)
    return str(resolved)


# ── Styles ────────────────────────────────────────────────────────────────────
GREEN_FILL   = PatternFill("solid", fgColor="C6EFCE")
RED_FILL     = PatternFill("solid", fgColor="FFC7CE")
ORANGE_FILL  = PatternFill("solid", fgColor="FFEB9C")
HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
SUMMARY_FILL = PatternFill("solid", fgColor="2E75B6")
WHITE_FONT   = Font(bold=True, color="FFFFFF")
BOLD_FONT    = Font(bold=True)
CENTER       = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT         = Alignment(horizontal="left",   vertical="center", wrap_text=True)
_thin        = Side(style="thin", color="BFBFBF")
BORDER       = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


# ── Query helpers ─────────────────────────────────────────────────────────────
class QueryError(Exception):
    pass


def run_tooling_query(query, username, fatal=True):
    sf_path = shutil.which("sf") or "sf"
    result = subprocess.run(
        [sf_path, "data", "query", "--query", query,
         "--target-org", username, "--use-tooling-api", "--json"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        msg = f"Could not parse CLI output:\n{result.stdout}\n{result.stderr}"
        if fatal:
            print(f"ERROR: {msg}")
            sys.exit(2)
        raise QueryError(msg)
    if data.get("status") != 0:
        msg = data.get('message', result.stderr)
        if fatal:
            print(f"ERROR: SOQL query failed: {msg}")
            sys.exit(2)
        raise QueryError(msg)
    return data.get("result", {}).get("records", [])


def fetch_all_coverage(username):
    """Fetch ALL ApexCodeCoverageAggregate records in chunks."""
    print(f"Querying ApexCodeCoverageAggregate from org: {username}")
    name_records = run_tooling_query(
        "SELECT ApexClassOrTrigger.Name FROM ApexCodeCoverageAggregate "
        "ORDER BY ApexClassOrTrigger.Name",
        username
    )
    all_names = [
        r.get("ApexClassOrTrigger", {}).get("Name", "")
        for r in name_records
        if r.get("ApexClassOrTrigger", {}).get("Name")
    ]
    print(f"Found {len(all_names)} classes with coverage records")
    if not all_names:
        print("ERROR: No coverage records found. Ensure tests have been run.")
        sys.exit(2)

    coverage_map = {}
    for i in range(0, len(all_names), CHUNK_SIZE):
        chunk    = all_names[i:i + CHUNK_SIZE]
        names_in = ", ".join(f"'{n}'" for n in chunk)
        records  = run_tooling_query(
            f"SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered "
            f"FROM ApexCodeCoverageAggregate "
            f"WHERE ApexClassOrTrigger.Name IN ({names_in})",
            username
        )
        for r in records:
            name = r.get("ApexClassOrTrigger", {}).get("Name", "")
            if name:
                coverage_map[name] = (
                    int(r.get("NumLinesCovered",   0)),
                    int(r.get("NumLinesUncovered", 0))
                )
        print(f"  Fetched chunk {i // CHUNK_SIZE + 1}: {len(records)} records")
    return coverage_map


def fetch_uncovered_lines(username, class_names):
    """
    Query ApexCodeCoverage for uncovered line numbers per class.
    Returns dict: { class_name: [line, line, ...] }
    Only fetches for classes that are below threshold to keep query count low.
    """
    print(f"\nFetching uncovered line numbers for {len(class_names)} failing classes...")
    uncovered_map = {}
    for i in range(0, len(class_names), CHUNK_SIZE):
        chunk    = class_names[i:i + CHUNK_SIZE]
        names_in = ", ".join(f"'{n}'" for n in chunk)
        records  = run_tooling_query(
            f"SELECT ApexClassOrTrigger.Name, Coverage "
            f"FROM ApexCodeCoverage "
            f"WHERE ApexClassOrTrigger.Name IN ({names_in})",
            username
        )
        for r in records:
            name     = r.get("ApexClassOrTrigger", {}).get("Name", "")
            coverage = r.get("Coverage", {}) or {}
            lines    = coverage.get("uncoveredLines", [])
            if name and lines:
                # merge lines if multiple test classes cover same production class
                existing = uncovered_map.get(name, set())
                existing.update(int(l) for l in lines)
                uncovered_map[name] = existing
    # sort line numbers
    return {k: sorted(v) for k, v in uncovered_map.items()}


def fetch_failed_tests(username):
    """
    Query ApexTestResult for all FAIL outcomes from the most recent test run.
    Returns list of dicts with keys: TestClass, Method, Message, StackTrace, LineNumber.
    """
    print("\nFetching failed test method details...")
    all_records = []
    offset = 0
    while True:
        try:
            batch = run_tooling_query(
                "SELECT ApexClass.Name, MethodName, Message, StackTrace "
                "FROM ApexTestResult "
                "WHERE Outcome = 'Fail' "
                "ORDER BY ApexClass.Name, MethodName "
                f"LIMIT 500 OFFSET {offset}",
                username,
                fatal=False
            )
        except QueryError as exc:
            print(f"WARNING: Stopped paginating failed tests at offset {offset}: {exc}")
            break
        all_records.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    results = []
    for r in all_records:
        class_name   = r.get("ApexClass", {}).get("Name", "Unknown")
        method       = r.get("MethodName", "")
        message      = r.get("Message",    "") or ""
        stack        = r.get("StackTrace", "") or ""
        line_num = ""
        for part in stack.split("\n"):
            if "line " in part:
                try:
                    line_num = part.strip().split("line ")[1].split(",")[0].strip()
                    break
                except (IndexError, AttributeError) as exc:
                    logging.debug("Could not parse line number from stack trace part %r: %s", part, exc)
        results.append({
            "TestClass":   class_name,
            "Method":      method,
            "Message":     message.strip(),
            "StackTrace":  stack.strip(),
            "LineNumber":  line_num,
        })
    print(f"  Found {len(results)} failed test method(s)")
    return results


# ── Coverage table ────────────────────────────────────────────────────────────
def build_rows(coverage_map):
    pass_rows, fail_rows = [], []
    print(f"\n{'Class':<60} {'Covered':>8} {'Total':>8} {'Coverage':>10}")
    print("-" * 92)
    for name, (covered, uncovered) in sorted(coverage_map.items()):
        total = covered + uncovered
        if total == 0:
            print(f"{name:<60} {'N/A':>8} {'N/A':>8} {'NO DATA':>10}  FAIL")
            fail_rows.append((name, "N/A", "N/A", 0.0, "FAIL"))
        else:
            pct    = (covered / total) * 100
            status = "PASS" if pct >= THRESHOLD else "FAIL"
            print(f"{name:<60} {covered:>8} {total:>8} {pct:>9.1f}%  {status}")
            row = (name, covered, total, pct, status)
            (pass_rows if status == "PASS" else fail_rows).append(row)
    print("-" * 92)
    fail_rows.sort(key=lambda x: x[3])
    return pass_rows, fail_rows


# ── Excel report ──────────────────────────────────────────────────────────────
def generate_excel(pass_rows, fail_rows, env, report_time,
                   output_dir, timestamp, uncovered_map, failed_tests):
    all_rows = fail_rows + pass_rows
    # output_dir already resolved + validated in main(); join with safe filename only
    xlsx_path = Path(output_dir) / f"coverage-report-{env}_{timestamp}.xlsx"
    wb = Workbook()

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 20
    no_data_count = sum(1 for r in fail_rows if r[1] == "N/A")
    for row_num, (label, value) in enumerate([
        ("Org / Environment",  env),
        ("Report Generated",   report_time),
        ("Coverage Threshold", f"{THRESHOLD}%"),
        ("Total Classes",      len(all_rows)),
        ("Passing Classes",    len(pass_rows)),
        ("Failing Classes",    len(fail_rows)),
        ("No Data Classes",    no_data_count),
        ("Failed Test Methods", len(failed_tests)),
    ], start=1):
        c1 = ws.cell(row_num, 1, label)
        c2 = ws.cell(row_num, 2, value)
        c1.fill = SUMMARY_FILL; c1.font = WHITE_FONT; c1.border = BORDER; c1.alignment = LEFT
        c2.border = BORDER; c2.alignment = LEFT
        if label == "Passing Classes":     c2.fill = GREEN_FILL;  c2.font = BOLD_FONT
        elif label == "Failing Classes":   c2.fill = RED_FILL;    c2.font = BOLD_FONT
        elif label == "Failed Test Methods" and failed_tests:
                                           c2.fill = RED_FILL;    c2.font = BOLD_FONT

    # ── Sheet 2: Coverage Detail ──────────────────────────────────────────────
    cov_headers    = ["#", "Class Name", "Covered Lines", "Total Lines", "Coverage %", "Status", "Uncovered Lines"]
    cov_widths     = [5, 45, 14, 12, 12, 10, 60]

    def write_coverage_sheet(ws, rows):
        for col, (h, w) in enumerate(zip(cov_headers, cov_widths), start=1):
            cell = ws.cell(1, col, h)
            cell.fill = HEADER_FILL; cell.font = WHITE_FONT
            cell.alignment = CENTER; cell.border = BORDER
            ws.column_dimensions[get_column_letter(col)].width = w
        ws.row_dimensions[1].height = 20
        for idx, (name, covered, total, pct, status) in enumerate(rows, start=1):
            fill        = GREEN_FILL if status == "PASS" else (ORANGE_FILL if covered == "N/A" else RED_FILL)
            pct_display = f"{pct:.1f}%" if covered != "N/A" else "NO DATA"
            unc_lines   = uncovered_map.get(name, [])
            unc_str     = ", ".join(str(l) for l in unc_lines) if unc_lines else ("N/A" if covered == "N/A" else "—")
            for col, val in enumerate([idx, name, covered, total, pct_display, status, unc_str], start=1):
                cell = ws.cell(idx + 1, col, val)
                cell.fill = fill; cell.border = BORDER
                cell.alignment = LEFT if col in (2, 7) else CENTER
            ws.row_dimensions[idx + 1].height = 30

    write_coverage_sheet(wb.create_sheet("Coverage Detail"), all_rows)

    ws_fail = wb.create_sheet("Below Threshold")
    if fail_rows:
        write_coverage_sheet(ws_fail, fail_rows)
    else:
        ws_fail.cell(2, 1, "All classes meet the coverage threshold").font = Font(bold=True, color="375623")

    # ── Sheet 3: Failed Tests ─────────────────────────────────────────────────
    ws_ft = wb.create_sheet("Failed Tests")
    ft_headers = ["#", "Test Class", "Method Name", "Line Number", "Error Message", "Stack Trace"]
    ft_widths  = [5, 40, 40, 12, 60, 80]
    for col, (h, w) in enumerate(zip(ft_headers, ft_widths), start=1):
        cell = ws_ft.cell(1, col, h)
        cell.fill = HEADER_FILL; cell.font = WHITE_FONT
        cell.alignment = CENTER; cell.border = BORDER
        ws_ft.column_dimensions[get_column_letter(col)].width = w
    ws_ft.row_dimensions[1].height = 20
    if failed_tests:
        for idx, ft in enumerate(failed_tests, start=1):
            fill = RED_FILL
            for col, val in enumerate([
                idx,
                ft["TestClass"],
                ft["Method"],
                ft["LineNumber"],
                ft["Message"],
                ft["StackTrace"],
            ], start=1):
                cell = ws_ft.cell(idx + 1, col, val)
                cell.fill = fill; cell.border = BORDER
                cell.alignment = LEFT if col > 1 else CENTER
            ws_ft.row_dimensions[idx + 1].height = 40
    else:
        ws_ft.cell(2, 1, "No test failures found").font = Font(bold=True, color="375623")

    wb.save(str(xlsx_path))
    print(f"\nExcel saved: {xlsx_path}")
    return str(xlsx_path)


def write_raw_log(pass_rows, fail_rows, env):
    # env already validated as alphanumeric in main()
    log_path = Path("/tmp") / f"coverage_raw_{env.lower()}.txt"
    with open(str(log_path), "w") as f:
        for name, covered, total, pct, status in fail_rows + pass_rows:
            if covered == "N/A":
                f.write(f"{name}  N/A  N/A  NO DATA  FAIL\n")
            else:
                f.write(f"{name}  {covered}  {total}  {pct:.1f}%  {status}\n")
    return str(log_path)


# ── Markdown summary ──────────────────────────────────────────────────────────
def _md_escape(value):
    """Escape value for safe inclusion in a markdown table cell."""
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def generate_markdown(pass_rows, fail_rows, env, report_time,
                      output_dir, uncovered_map, failed_tests):
    # output_dir already resolved + validated; env already validated as alphanumeric
    md_path = Path(output_dir) / f"coverage-report-{env.lower()}.md"
    with open(str(md_path), "w", encoding="utf-8") as f:
        f.write(f"## Apex Code Coverage Report - {_md_escape(env)}\n\n")
        f.write(f"**Run Time:** {_md_escape(report_time)}  \n")
        f.write(f"**Threshold:** {THRESHOLD}%  \n")
        f.write(f"**Total Classes:** {len(pass_rows) + len(fail_rows)}  \n")
        f.write(f"**Passing:** {len(pass_rows)}  \n")
        f.write(f"**Failing:** {len(fail_rows)}  \n")
        f.write(f"**Failed Test Methods:** {len(failed_tests)}  \n\n")

        # Failed test methods
        if failed_tests:
            f.write("### Failed Test Methods\n\n")
            f.write("| Test Class | Method | Line | Error |\n")
            f.write("|---|---|---|---|\n")
            for ft in failed_tests:
                msg = _md_escape(ft["Message"])[:200]
                f.write(f"| {_md_escape(ft['TestClass'])} | {_md_escape(ft['Method'])} | {_md_escape(ft['LineNumber'])} | {msg} |\n")
            f.write("\n")

        # Classes below threshold
        if fail_rows:
            f.write(f"### Classes Below {THRESHOLD}%\n\n")
            f.write("| Class | Covered | Total | Coverage | Uncovered Lines |\n")
            f.write("|---|---|---|---|---|\n")
            for name, covered, total, pct, _ in fail_rows:
                cov_str = "N/A" if covered == "N/A" else str(covered)
                tot_str = "N/A" if total   == "N/A" else str(total)
                pct_str = "NO DATA" if covered == "N/A" else f"{pct:.1f}%"
                unc     = uncovered_map.get(name, [])
                unc_str = ", ".join(str(l) for l in unc[:20])
                if len(unc) > 20:
                    unc_str += f" ... (+{len(unc)-20} more)"
                if not unc_str:
                    unc_str = "N/A" if covered == "N/A" else "—"
                f.write(f"| {_md_escape(name)} | {cov_str} | {tot_str} | {pct_str} | {unc_str} |\n")
            f.write("\n")

        # Classes passing
        if pass_rows:
            f.write(f"### Classes Meeting {THRESHOLD}%\n\n")
            f.write("| Class | Covered | Total | Coverage |\n")
            f.write("|---|---|---|---|\n")
            for name, covered, total, pct, _ in pass_rows:
                f.write(f"| {_md_escape(name)} | {covered} | {total} | {pct:.1f}% |\n")
    return str(md_path)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username",   required=True)
    parser.add_argument("--env",        required=True)
    parser.add_argument("--timestamp",  required=True)
    parser.add_argument("--output-dir", required=True, dest="output_dir")
    args = parser.parse_args()

    # Validate args used in file paths to prevent path traversal
    _safe_arg(args.env,       "env")
    _safe_arg(args.timestamp, "timestamp")
    output_dir = _safe_output_dir(args.output_dir)

    report_time = os.environ.get("REPORT_TIME") or ""
    if isinstance(report_time, list):
        report_time = " ".join(report_time)
    report_time = str(report_time).strip("[]'\"")

    coverage_map = fetch_all_coverage(args.username)
    pass_rows, fail_rows = build_rows(coverage_map)

    # fetch uncovered lines only for failing classes (skip NO DATA ones)
    failing_class_names = [name for name, covered, *_ in fail_rows if covered != "N/A"]
    uncovered_map = fetch_uncovered_lines(args.username, failing_class_names) if failing_class_names else {}

    # fetch failed test method details
    failed_tests = fetch_failed_tests(args.username)

    generate_excel(pass_rows, fail_rows, args.env, report_time,
                   output_dir, args.timestamp, uncovered_map, failed_tests)
    md_path = generate_markdown(pass_rows, fail_rows, args.env, report_time,
                                output_dir, uncovered_map, failed_tests)
    write_raw_log(pass_rows, fail_rows, args.env)
    print(f"Markdown saved: {md_path}")

    total = len(pass_rows) + len(fail_rows)
    print(f"\nTotal: {total} | Pass: {len(pass_rows)} | Fail: {len(fail_rows)} | Failed Tests: {len(failed_tests)}")

    if failed_tests:
        print(f"\nFAILED TEST METHODS ({len(failed_tests)}):")
        for ft in failed_tests:
            print(f"  {ft['TestClass']}.{ft['Method']} (line {ft['LineNumber']}): {ft['Message'][:120]}")

    if fail_rows:
        print(f"\nCOVERAGE CHECK FAILED - {len(fail_rows)} class(es) below {THRESHOLD}%.")
        sys.exit(1)

    print(f"\nCOVERAGE CHECK PASSED - all {len(pass_rows)} class(es) meet {THRESHOLD}%")
    sys.exit(0)


if __name__ == "__main__":
    main()
