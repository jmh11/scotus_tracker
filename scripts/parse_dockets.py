#!/usr/bin/env python3
"""Turn the raw docket files into the tracker's case facts, using fixed rules.

Input:  data/raw/dockets/<docket>.json  (saved unchanged by fetch_raw.py)
Output: data/parsed_dockets.json        (one record per docket)

Rules, applied to the Court's own docket entries:
  granted     date of the entry that grants the petition
              (text contains "Petition GRANTED", "petition for a writ of certiorari GRANTED"
              or "probable jurisdiction noted"; case-insensitive)
  scheduled   the date named in the most recent "SET FOR ARGUMENT on <Weekday>, <Month D, YYYY>" entry
  argued      date of the entry whose text begins "Argued."
  lowerCourt, petitionerTitle, respondentTitle, qpUrl: copied from the docket's own fields

If a rule finds something it can't handle (no grant entry, two different grant dates,
an argument date it can't read), the script reports it and exits with an error.
It never guesses.
"""
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "dockets"
OUT = ROOT / "data" / "parsed_dockets.json"

GRANT_RE = re.compile(r"Petition GRANTED|petition for a writ of certiorari GRANTED|probable jurisdiction noted", re.I)
SET_RE = re.compile(r"SET FOR ARGUMENT on (?:Monday|Tuesday|Wednesday|Thursday|Friday), ([A-Z][a-z]+ \d{1,2}, \d{4})")
ARGUED_RE = re.compile(r"^Argued\.")
QP_BASE = "https://www.supremecourt.gov/qp/"


def entry_date(s: str) -> str:
    """Docket entry dates look like 'Jun 29 2026'."""
    return dt.datetime.strptime(s.strip(), "%b %d %Y").date().isoformat()


def text_date(s: str) -> str:
    """Dates inside entry text look like 'November 9, 2026'."""
    return dt.datetime.strptime(s.strip(), "%B %d, %Y").date().isoformat()


def parse(path: pathlib.Path):
    j = json.loads(path.read_text(encoding="utf-8-sig"))
    problems = []
    m = re.match(r"\s*(\d{2}-\d{1,5})\b", j.get("CaseNumber") or "")
    docket = m.group(1) if m else path.stem
    if not m or docket != path.stem:
        problems.append(f"case number {j.get('CaseNumber')!r} doesn't match file {path.name}")
    grants, sets, argued = set(), [], set()
    for e in j.get("ProceedingsandOrder") or []:
        text = (e.get("Text") or "").strip()
        try:
            when = entry_date(e["Date"])
        except (KeyError, ValueError):
            problems.append(f"unreadable entry date {e.get('Date')!r}")
            continue
        if GRANT_RE.search(text):
            grants.add(when)
        m = SET_RE.search(text)
        if m:
            sets.append((when, text_date(m.group(1))))
        elif "SET FOR ARGUMENT" in text.upper():
            problems.append(f"argument entry in an unexpected format: {text[:80]!r}")
        if ARGUED_RE.match(text):
            argued.add(when)

    if len(grants) != 1:
        problems.append(f"expected one grant date, found {sorted(grants) or 'none'}")
    if len(argued) > 1:
        problems.append(f"more than one 'Argued.' date: {sorted(argued)}")
    qp = j.get("QPLink") or ""
    rec = {
        "docket": docket,
        "capitalCase": bool(j.get("bCapitalCase")),
        "petitionerTitle": (j.get("PetitionerTitle") or "").strip(),
        "respondentTitle": (j.get("RespondentTitle") or "").strip(),
        "lowerCourt": (j.get("LowerCourt") or "").strip(),
        "granted": min(grants) if grants else None,
        "scheduled": max(sets)[1] if sets else None,   # latest scheduling entry wins
        "argued": min(argued) if argued else None,
        "qpUrl": QP_BASE + qp.split("/qp/")[-1] if "/qp/" in qp else None,
        "docketJsonCreated": j.get("sJsonCreationDate"),
    }
    return rec, problems


def main() -> int:
    records, failures = [], {}
    for path in sorted(RAW.glob("*.json")):
        rec, problems = parse(path)
        records.append(rec)
        if problems:
            failures[rec["docket"]] = problems
    OUT.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n")
    print(f"Parsed {len(records)} dockets into {OUT.relative_to(ROOT)}.")
    for d, ps in failures.items():
        for p in ps:
            print(f"PROBLEM {d}: {p}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
