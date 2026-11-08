#!/usr/bin/env python3
"""Turn the raw docket files into the tracker's case facts, using fixed rules.

Input:  data/raw/dockets/<docket>.json  (saved unchanged by fetch_raw.py)
Output: data/parsed_dockets.json        (one record per docket)

Rules, applied to the Court's own docket entries:
  granted     date of the entry that grants the petition: text contains "Petition GRANTED",
              "petition for a writ of certiorari [before judgment] [is] GRANTED", "probable jurisdiction noted",
              or "treated as a petition for a writ of certiorari ..., and the petition is granted"
              (an emergency application converted to a petition); case-insensitive.
              Entries beginning "The order granting the petition ... is amended" are not new grants.
  scheduled   the date named in the most recent "SET FOR ARGUMENT on <Weekday>, <Month D, YYYY>" entry
  argued      date of the entry whose text begins "Argued."
  decided     date of the decision entry: its first sentence begins "Judgment ... AFFIRMED/REVERSED/
              VACATED/DISMISSED", "Adjudged to be ..." or "Writ of certiorari ..."
  outcome     from that entry's judgment words for this docket: AFFIRMED -> affirm, REVERSED -> reverse,
              VACATED -> vacate, DISMISSED -> dismissed; "IN PART" or two different verbs -> mixed.
              In consolidated cases, a clause naming "No. X" applies only to docket X.
  opinionUrl  the opinion link inside that entry
  meritsBriefs  each party's merits brief after the grant ("Brief of petitioner(s)/respondent(s) ... filed",
              "Reply of ... filed"), excluding opposition briefs, amicus briefs and petition-stage filings
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

GRANT_RE = re.compile(
    r"Petition GRANTED"
    r"|petition for (?:a )?writ of certiorari(?: before judgment)?(?: is)? GRANTED"
    r"|probable jurisdiction noted"
    r"|treated as (?:a )?petitions? for (?:a )?writs? of certiorari[^.]*?, and the petitions? (?:is|are) granted",
    re.I)
# An entry that amends an earlier grant order is not a new grant.
GRANT_AMENDMENT_RE = re.compile(r"^The order granting the petition[^.]* is amended", re.I)
# A decision entry's first sentence begins with one of these and names a judgment.
DECISION_START_RE = re.compile(r"^(?:Judgment(?: in No\. [\d-]+)?(?: is)?|Adjudged to be|Writ of certiorari) (?:AFFIRMED|REVERSED|VACATED|DISMISSED)")
OPINION_LINK_RE = re.compile(r"href\s*=\s*'(https://www\.supremecourt\.gov/opinions/[^']+\.pdf)'")
VERBS = ("AFFIRMED", "REVERSED", "VACATED", "DISMISSED")
SET_RE = re.compile(r"SET FOR ARGUMENT on (?:Monday|Tuesday|Wednesday|Thursday|Friday), ([A-Z][a-z]+ \d{1,2}, \d{4})")
ARGUED_RE = re.compile(r"^Argued\.")
QP_BASE = "https://www.supremecourt.gov/qp/"
# Consolidated cases: "... future filings and activity in the cases will now be reflected on the docket of No. 25-238."
FILINGS_ON_RE = re.compile(r"future filings and activity in the cases will now be reflected on the docket of No\. ([\d-]+)")
# A party's merits brief: "Brief of petitioner ... filed", "Brief of respondents ... filed",
# "Brief for the respondent ... supporting vacatur filed", "Reply of petitioner ... filed".
# A lawyer the Court appoints to argue a side counts too: "Brief of Court-appointed amicus curiae ... filed".
# Opposition briefs ("in opposition"), other amicus briefs, briefs "not accepted for filing" and anything
# filed on or before the grant date (the petition stage) are not merits briefs.
BRIEF_RE = re.compile(r"^(Brief|Reply) (?:of|for) (?:the )?(petitioners?|respondents?|court-appointed amicus curiae)\b"
                      r".*\bfiled\b", re.I)
BRIEF_KINDS = {("brief", "petitioner"): "Petitioner's brief", ("brief", "respondent"): "Respondent's brief",
               ("reply", "petitioner"): "Petitioner's reply brief", ("reply", "respondent"): "Respondent's reply brief",
               ("brief", "amicus"): "Court-appointed amicus brief",
               ("reply", "amicus"): "Court-appointed amicus reply brief"}


def brief_side(word: str) -> str:
    """'petitioners' -> 'petitioner', 'Court-appointed amicus curiae' -> 'amicus'."""
    w = word.lower()
    return "amicus" if w.startswith("court-appointed") else w.rstrip("s")


def entry_date(s: str) -> str:
    """Docket entry dates look like 'Jun 29 2026'."""
    return dt.datetime.strptime(s.strip(), "%b %d %Y").date().isoformat()


def text_date(s: str) -> str:
    """Dates inside entry text look like 'November 9, 2026'."""
    return dt.datetime.strptime(s.strip(), "%B %d, %Y").date().isoformat()


def judgment_for(docket: str, text: str):
    """Return (outcome, judgment wording) for this docket from a decision entry, or raise ValueError.

    The judgment part is everything before the first link or the first "delivered"/"per curiam".
    It is split into clauses at '.' and ';'. A clause naming "No. X" belongs to docket X;
    a clause naming no case belongs to the docket whose file this is.
    """
    head = re.split(r"<a |delivered|[Pp]er [Cc]uriam", text)[0]
    mine = []
    for clause in re.split(r"(?<!No)[.;]\s+", head):
        named = re.search(r"No\. ([\d-]+)", clause)
        if named and named.group(1) != docket:
            continue
        if any(v in clause for v in VERBS):
            mine.append(clause.strip())
    if not mine:
        raise ValueError(f"no judgment for {docket} in {head[:100]!r}")
    words = " ".join(mine)
    found = {v for v in VERBS if v in words}
    if "IN PART" in words or len(found) > 1:
        return "mixed", words
    return {"AFFIRMED": "affirm", "REVERSED": "reverse", "VACATED": "vacate", "DISMISSED": "dismissed"}[found.pop()], words


def parse(path: pathlib.Path):
    j = json.loads(path.read_text(encoding="utf-8-sig"))
    problems = []
    m = re.match(r"\s*(\d{2}-\d{1,5})\b", j.get("CaseNumber") or "")
    docket = m.group(1) if m else path.stem
    if not m or docket != path.stem:
        problems.append(f"case number {j.get('CaseNumber')!r} doesn't match file {path.name}")
    grants, sets, argued, decisions, brief_candidates = set(), [], set(), [], []
    filings_on = None
    for e in j.get("ProceedingsandOrder") or []:
        text = (e.get("Text") or "").strip()
        try:
            when = entry_date(e["Date"])
        except (KeyError, ValueError):
            problems.append(f"unreadable entry date {e.get('Date')!r}")
            continue
        if GRANT_RE.search(text) and not GRANT_AMENDMENT_RE.match(text):
            grants.add(when)
        m = SET_RE.search(text)
        if m:
            sets.append((when, text_date(m.group(1))))
        elif text.upper().startswith("SET FOR ARGUMENT"):
            problems.append(f"argument entry in an unexpected format: {text[:80]!r}")
        b = BRIEF_RE.match(text)
        if b and "in opposition" not in text.lower():
            kind = BRIEF_KINDS[(b.group(1).lower(), brief_side(b.group(2)))]
            main = next((l.get("DocumentUrl") for l in e.get("Links") or [] if l.get("Description") == "Main Document"), None)
            brief_candidates.append({"date": when, "kind": kind, "url": main})
        f = FILINGS_ON_RE.search(text)
        if f:
            filings_on = f.group(1)
        if ARGUED_RE.match(text):
            argued.add(when)
        if DECISION_START_RE.match(text):
            try:
                outcome, words = judgment_for(docket, text)
            except ValueError as err:
                problems.append(str(err))
                continue
            link = OPINION_LINK_RE.search(text)
            decisions.append({"decided": when, "outcome": outcome, "judgmentText": words,
                              "opinionUrl": link.group(1) if link else None})

    if len(grants) != 1:
        problems.append(f"expected one grant date, found {sorted(grants) or 'none'}")
    if len(decisions) > 1:
        problems.append(f"more than one decision entry: {[d['decided'] for d in decisions]}")
    qp = j.get("QPLink") or ""
    rec = {
        "docket": docket,
        "capitalCase": bool(j.get("bCapitalCase")),
        "petitionerTitle": (j.get("PetitionerTitle") or "").strip(),
        "respondentTitle": (j.get("RespondentTitle") or "").strip(),
        "lowerCourt": (j.get("LowerCourt") or "").strip(),
        "granted": min(grants) if grants else None,
        "scheduled": max(sets)[1] if sets else None,   # latest scheduling entry wins
        "argued": max(argued) if argued else None,     # a reargued case keeps its latest argument
        "reargued": len(argued) > 1,
        "decided": decisions[-1]["decided"] if decisions else None,
        "outcome": decisions[-1]["outcome"] if decisions else None,
        "judgmentText": decisions[-1]["judgmentText"] if decisions else None,
        "opinionUrl": decisions[-1]["opinionUrl"] if decisions else None,
        "meritsBriefs": [b for b in brief_candidates if grants and b["date"] > min(grants)],
        # Another docket that holds this case's filings after consolidation (None if it's this one).
        "filingsOn": filings_on if filings_on != docket else None,
        "qpUrl": QP_BASE + qp.split("/qp/")[-1] if "/qp/" in qp else None,
        "docketJsonCreated": j.get("sJsonCreationDate"),
    }
    return rec, problems


def main() -> int:
    raw, out = RAW, OUT
    if len(sys.argv) == 3:  # optional: parse_dockets.py <raw dir> <output file>, used for testing
        raw, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    records, failures = [], {}
    for path in sorted(raw.glob("*.json")):
        rec, problems = parse(path)
        records.append(rec)
        if problems:
            failures[rec["docket"]] = problems
    out.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n")
    print(f"Parsed {len(records)} dockets into {out}.")
    for d, ps in failures.items():
        for p in ps:
            print(f"PROBLEM {d}: {p}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
