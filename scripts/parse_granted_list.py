#!/usr/bin/env python3
"""Read the Granted & Noted list with fixed rules and find cases the tracker doesn't have yet.

Input:  data/raw/granted_noted_list.pdf (saved unchanged by fetch_raw.py)
        data/tracked_dockets.txt
Output: data/granted_list.json  every case on the list, as listed
        printed report of docket numbers on the list that aren't tracked

Text is extracted with `pdftotext -layout` (poppler). Rules:
  case line     "<docket>[)<n>]  <3-letter code>  <CAPTION>"   e.g. "25-238)1   CFX   VIRAMONTES V. COOK COUNTY"
  court/grant   "Court: <court codes>  Granted: M/D/YY"        applies to the case line(s) just above it
  argument      "Argument Date: M/D/YY"                        optional
  consolidated  cases may share one Court/Granted line only if the list marks them ")1", ")2", ...
  NOTE section  cases after the line "NOTE:" were disposed of without argument ("Result: ...")
  self-check    the number of cases found must equal "Total Cases (Arguments) Made Available: N"

Anything that doesn't fit these rules stops the script with an error. Nothing is guessed.
"""
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "raw" / "granted_noted_list.pdf"
OUT = ROOT / "data" / "granted_list.json"
TRACKED = ROOT / "data" / "tracked_dockets.txt"

CASE_RE = re.compile(r"^\s*(\d{2}-\d{1,5})(?:\)(\d))?\s+([CAQ][SFTMO][XYH])\s+(\S.*?)\s*$")
GRANT_RE = re.compile(r"^\s*Court:\s*(.+?)\s+Granted:\s*(\d{1,2}/\d{1,2}/\d{2})\s*$")
ARG_RE = re.compile(r"^\s*Argument Date:\s*(\d{1,2}/\d{1,2}/\d{2})\s*$")
RESULT_RE = re.compile(r"^\s*Result:\s*(.+?)\s*$")
ASOF_RE = re.compile(r"^\s*As of ([A-Z][a-z]+ \d{1,2}, \d{4})\s*$")
TOTAL_RE = re.compile(r"Total Cases \(Arguments\) Made Available:\s*(\d+)")


def mdy(s: str) -> str:
    return dt.datetime.strptime(s, "%m/%d/%y").date().isoformat()


def parse(text: str):
    cases, pending, block, problems = [], [], [], []
    in_note, as_of, total = False, None, None
    for n, line in enumerate(text.splitlines(), 1):
        if m := ASOF_RE.match(line):
            as_of = dt.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
        elif line.strip() == "NOTE:":
            in_note = True
        elif m := CASE_RE.match(line):
            pending.append({"docket": m.group(1), "group": m.group(2), "code": m.group(3),
                            "captionAsListed": m.group(4), "section": "note" if in_note else "for argument"})
        elif m := GRANT_RE.match(line):
            if not pending:
                problems.append(f"line {n}: 'Court/Granted' line with no case above it")
                continue
            if len(pending) > 1 and any(c["group"] is None for c in pending):
                problems.append(f"line {n}: cases {[c['docket'] for c in pending]} share one 'Court/Granted' "
                                "line but aren't marked as consolidated")
            for c in pending:
                c["courtCodes"], c["granted"] = m.group(1), mdy(m.group(2))
                c["argumentDate"], c["result"] = None, None
            cases.extend(pending)
            block, pending = pending, []
        elif line.strip().startswith(("Court:", "Argument Date:")) and not ARG_RE.match(line):
            problems.append(f"line {n}: unexpected layout: {line.strip()[:80]!r}")
        elif m := ARG_RE.match(line):
            if not block:
                problems.append(f"line {n}: argument date not directly under a case block")
                continue
            for c in block:  # applies only to the block directly above
                c["argumentDate"] = mdy(m.group(1))
        elif CASE_RE.match(line) is None and line.strip() and not line.startswith((" ", "\t")):
            block = []  # any other unindented text ends the current block
        elif m := RESULT_RE.match(line):
            if cases and cases[-1]["section"] == "note":
                cases[-1]["result"] = m.group(1)
        if m := TOTAL_RE.search(line):
            total = int(m.group(1))
    if pending:
        problems.append(f"case line(s) without a 'Court/Granted' line: {[c['docket'] for c in pending]}")
    if as_of is None:
        problems.append("no 'As of' date found")
    if total is None:
        problems.append("no 'Total Cases ... Made Available' line found")
    elif total != len(cases):
        problems.append(f"the list says {total} cases; the rules found {len(cases)}")
    return {"asOf": as_of, "statedTotal": total, "cases": cases}, problems


def main() -> int:
    text = subprocess.run(["pdftotext", "-layout", str(PDF), "-"], check=True,
                          capture_output=True, text=True).stdout
    result, problems = parse(text)
    for p in problems:
        print(f"PROBLEM {p}")
    if problems:
        return 1
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    tracked = {d.strip() for d in TRACKED.read_text().splitlines() if d.strip()}
    for_argument = [c for c in result["cases"] if c["section"] == "for argument"]
    new = [c for c in for_argument if c["docket"] not in tracked]
    gone = sorted(tracked - {c["docket"] for c in for_argument})
    print(f"Granted list as of {result['asOf']}: {len(result['cases'])} cases "
          f"({len(for_argument)} for argument, {len(result['cases']) - len(for_argument)} in the NOTE section).")
    print(f"New (on the list, not tracked): {[c['docket'] for c in new] or 'none'}")
    print(f"Tracked but no longer listed for argument: {gone or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
