#!/usr/bin/env python3
"""Build the page's data file from the parsed official data and Joshua's approved files.

Inputs (all in data/):
  granted_list.json    from parse_granted_list.py
  parsed_dockets.json  from parse_dockets.py
  tracked_dockets.txt  tracked cases (this script adds new grants to it)
  display_names.json   approved names        court_names.json  court-name lookup
  content.json         approved write-ups     config.json       term, cutoff, email
  transcripts.json, audio.json  from parse_transcripts.py
  tags.json            hand-assigned tags (kinds of question, subjects), approved by Joshua
  changelog.json       running list of changes (this script appends to it)
Outputs:
  site/cases.json      what the page shows
  build_report.md      what changed, what needs Joshua's attention, and any problems

Fixed rules:
  - A case on the list "for argument" that isn't tracked is added if it was granted on or before
    the cutoff in config.json, otherwise reported and skipped.
  - A tracked case in the list's NOTE section (disposed of without argument) moves to "excluded".
  - Grant dates must agree between the list and the docket. Dates must run granted <= argued <= decided.
  - Every lower court must be in court_names.json. Unapproved names and missing write-ups are flagged.
  - Changes are found by comparing with the previous site/cases.json.
  - An argued case should have a transcript link; a missing one is flagged.
  - Review labels: an official question, a party's merits brief, or an argument transcript/audio
    that isn't listed in review_seen.json is flagged (and emailed the first time it appears).
  - Answer options in content.json: 2 to 4 per case, each with an id, label and meaning.
  - results.json records which option happened in a decided case (or "none"); a decided case
    without one is flagged, and the page shows "Result pending".
  - Tags in tags.json must be from its own lists. The Court's classification is added automatically
    from the third letter of the list's case code (X civil, Y criminal, H habeas) and the docket's
    capital-case flag.
If any check fails, nothing is written and the script exits with an error.

Usage: build.py [--today YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from names import display_name  # noqa: E402
from tracked import read_tracked, write_tracked  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "site" / "cases.json"
REPORT = ROOT / "build_report.md"
NOTIFY = ROOT / "notify.md"   # written only when there's news; the workflow turns it into a GitHub issue
OUTCOMES = {"affirm", "reverse", "vacate", "dismissed", "mixed"}
# "amicus" + "amicusHeading": an optional third side (e.g. a court-appointed lawyer), shown as a third column.
CONTENT_KEYS = {"question", "background", "facts", "petitioner", "respondent", "amicus", "amicusHeading", "options"}
OPTION_KEYS = {"id", "label", "meaning"}
COURT_CLASS = {"X": "Civil", "Y": "Criminal", "H": "Habeas"}
DOCKET_PAGE = "https://www.supremecourt.gov/docket/docketfiles/html/public/{}.html"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def consolidation_blocks(listed_cases):
    """Cases the list marks ')1', ')2', ... directly above one shared Court/Granted line."""
    partners, block = {}, []
    for c in listed_cases:
        if c.get("group") == "1":
            block = [c["docket"]]
        elif c.get("group") and block:
            block.append(c["docket"])
        else:
            block = []
            continue
        for d in block:
            partners[d] = [x for x in block if x != d]
    return partners


def fmt(iso):
    if not iso:
        return "not set"
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def diff(prev: dict, now: dict, excluded_now: list):
    """Plain-language changes between the previous and new case lists."""
    out, written = [], []
    labels = {"affirm": "affirmed", "reverse": "reversed", "vacate": "vacated and remanded",
              "dismissed": "dismissed", "mixed": "mixed result"}
    for d, c in now.items():
        p = prev.get(d)
        n = c["name"]
        if p is None:
            out.append(f"Added {n} (No. {d}), granted {fmt(c['granted'])}.")
            continue
        if c["argued"] and not p.get("argued"):
            out.append(f"{n} was argued on {fmt(c['argued'])}.")
        elif c["scheduled"] != p.get("scheduled") and c["scheduled"] and not c["argued"]:
            verb = "rescheduled" if p.get("scheduled") else "scheduled"
            out.append(f"{n}: argument {verb} for {fmt(c['scheduled'])}.")
        if c["decided"] and not p.get("decided"):
            out.append(f"{n} was decided on {fmt(c['decided'])}: {labels[c['outcome']]}.")
        if c["name"] != p.get("name"):
            out.append(f"No. {d} is now listed as {n}.")
        if c["content"] != p.get("content"):
            written.append(n)
    if written:  # one line for a batch, so a round of approvals doesn't flood the log
        out.append(f"Case write-ups added or updated for {len(written)} case(s)." if len(written) > 3
                   else f"Case write-ups added or updated for {', '.join(written)}.")
    for x in excluded_now:
        if x["docket"] in prev:
            out.append(f"{x['name']} (No. {x['docket']}) was removed from the argument docket: {x['result']}.")
    return out


def build(today: str):
    cfg = load("config.json")
    listed = load("granted_list.json")
    parsed = {r["docket"]: r for r in load("parsed_dockets.json")}
    names = {k: v for k, v in load("display_names.json").items() if not k.startswith("_")}
    courts = {k: v for k, v in load("court_names.json").items() if not k.startswith("_")}
    content = {k: v for k, v in load("content.json").items() if not k.startswith("_")}
    transcripts = load("transcripts.json") if (DATA / "transcripts.json").exists() else {}
    seen = load("review_seen.json") if (DATA / "review_seen.json").exists() else {"question": [], "briefs": {}, "argument": []}
    results = {k: v for k, v in load("results.json").items() if not k.startswith("_")} \
        if (DATA / "results.json").exists() else {}
    audio = load("audio.json") if (DATA / "audio.json").exists() else {}
    tagfile = load("tags.json")
    allowed = {"kinds": tagfile["kinds"], "subjects": tagfile["subjects"]}
    changelog = load("changelog.json") if (DATA / "changelog.json").exists() else []
    tracked = read_tracked()
    prev_site = json.loads(SITE_DATA.read_text()) if SITE_DATA.exists() else {"cases": [], "updatedAt": None}
    prev = {c["docket"]: c for c in prev_site["cases"]}

    problems, flags = [], []
    by_list = {c["docket"]: c for c in listed["cases"]}
    partners = consolidation_blocks(listed["cases"])

    # New grants
    for c in listed["cases"]:
        if c["section"] != "for argument" or c["docket"] in tracked:
            continue
        if c["granted"] <= cfg["newGrantCutoff"]:
            tracked[c["docket"]] = today
        else:
            flags.append(f"{c['docket']} ({c['captionAsListed']}) was granted {fmt(c['granted'])}, "
                         f"after the {fmt(cfg['newGrantCutoff'])} cutoff, so it was not added.")

    # Cases disposed of without argument
    excluded = []
    for d in tracked:
        lc = by_list.get(d)
        if lc and lc["section"] == "note":
            name, _ = display_name(d, names, lc["captionAsListed"])
            excluded.append({"docket": d, "name": name, "result": lc.get("result") or "disposed of without argument"})
    excluded_ids = {x["docket"] for x in excluded}

    cases = []
    for d, added in tracked.items():
        if d in excluded_ids:
            continue
        rec, lc = parsed.get(d), by_list.get(d)
        if rec is None:
            problems.append(f"{d}: no parsed docket data")
            continue
        if lc is None:
            flags.append(f"{d} is tracked but no longer appears on the Granted & Noted list.")
        if lc and lc["granted"] != rec["granted"]:
            problems.append(f"{d}: grant date is {lc['granted']} on the list but {rec['granted']} on the docket")
        if d in names:
            name, approved = names[d], True
        elif lc:
            name, approved = display_name(d, names, lc["captionAsListed"])
        else:
            problems.append(f"{d}: no approved name and not on the list to build one from")
            continue
        if not approved:
            flags.append(f"{d}: automatic name \"{name}\" needs your approval (add it to data/display_names.json).")
        court = courts.get(rec["lowerCourt"])
        if court is None:
            problems.append(f"{d}: lower court {rec['lowerCourt']!r} is missing from data/court_names.json")
            continue
        for a, b in (("granted", "argued"), ("argued", "decided"), ("granted", "decided")):
            if rec.get(a) and rec.get(b) and rec[b] < rec[a]:
                problems.append(f"{d}: {b} ({rec[b]}) is before {a} ({rec[a]})")
        if rec["decided"] and rec["outcome"] not in OUTCOMES:
            problems.append(f"{d}: unknown outcome {rec['outcome']!r}")
        assigned = tagfile["cases"].get(d)
        tags = {"kinds": [], "subjects": [], "court": []}
        if assigned is None:
            flags.append(f"{d}: no tags yet (add it to data/tags.json).")
        else:
            for fam in ("kinds", "subjects"):
                for t in assigned.get(fam, []):
                    if t not in allowed[fam]:
                        problems.append(f"{d}: tag {t!r} is not in the {fam} list in data/tags.json")
                    else:
                        tags[fam].append(t)
        if lc:
            cls = COURT_CLASS.get(lc["code"][2])
            if cls is None:
                problems.append(f"{d}: unknown case code {lc['code']!r} on the Granted list")
            else:
                tags["court"].append(cls)
        if rec.get("capitalCase"):
            tags["court"].append("Capital case")
        written = content.get(d)
        if written is not None:
            bad = set(written) - CONTENT_KEYS
            if bad:
                problems.append(f"{d}: content.json has unexpected fields {sorted(bad)}")
            if ("amicus" in written or "amicusHeading" in written) and not written.get("amicusHeading"):
                problems.append(f"{d}: a third side (\"amicus\") needs a heading (\"amicusHeading\")")
            opts = written.get("options")
            if opts is not None:
                ids = [o.get("id") for o in opts]
                if not 2 <= len(opts) <= 4:
                    problems.append(f"{d}: needs 2 to 4 answer options, has {len(opts)}")
                if len(set(ids)) != len(ids) or any(set(o) != OPTION_KEYS or not all(o.values()) for o in opts):
                    problems.append(f"{d}: each answer option needs a unique id, a label and a meaning")
        # Which answer happened, recorded by Joshua after a decision ("none" = no option fits).
        result = results.get(d)
        if result is not None:
            valid = {o["id"] for o in (written or {}).get("options", [])} | {"none"}
            if result not in valid:
                problems.append(f"{d}: results.json says {result!r}, which isn't one of this case's options")
            if not rec["decided"]:
                problems.append(f"{d}: results.json records an answer, but the case isn't decided")
        elif rec["decided"]:
            flags.append(f"{d}: decided {fmt(rec['decided'])}; record which answer happened in data/results.json.")
        cases.append({
            "docket": d, "name": name, "lowerCourt": court, "lowerCourtFull": rec["lowerCourt"],
            "granted": rec["granted"],
            "scheduled": rec["scheduled"] if not rec["argued"] else None,
            "argued": rec["argued"], "reargued": rec.get("reargued", False),
            "decided": rec["decided"], "outcome": rec["outcome"], "opinionUrl": rec["opinionUrl"],
            "qpUrl": rec["qpUrl"], "docketUrl": DOCKET_PAGE.format(d),
            # consolidated cases share one transcript, which may be filed under either docket
            "transcriptUrl": transcripts.get(d) or next((transcripts[x] for x in partners.get(d, []) if x in transcripts), None),
            "audioUrl": audio.get(d) or next((audio[x] for x in partners.get(d, []) if x in audio), None),
            "consolidatedWith": partners.get(d, []), "capitalCase": rec.get("capitalCase", False),
            "addedOn": added, "content": written, "tags": tags, "result": result,
            "meritsBriefs": rec.get("meritsBriefs", []), "filingsOn": rec.get("filingsOn"),
        })

    for d in tagfile["cases"]:
        if d not in tracked:
            flags.append(f"data/tags.json has tags for {d}, which isn't tracked.")
    names_by_docket = {c["docket"]: c["name"] for c in cases}
    for c in cases:
        c["consolidatedWith"] = [{"docket": x, "name": names_by_docket.get(x, x)} for x in c["consolidatedWith"]]
    # Main merits briefing is complete once the petitioner and respondent have each filed a main brief, plus the
    # Court-appointed lawyer when the case has a third side. Reply briefs aren't needed. The page uses this to
    # choose what an empty argument summary says.
    for c in cases:
        kinds = {b["kind"] for b in c["meritsBriefs"]}
        needed = {"Petitioner's brief", "Respondent's brief"}
        if (c["content"] or {}).get("amicusHeading"):
            needed.add("Court-appointed amicus brief")
        c["briefingComplete"] = needed <= kinds
    # A consolidated case whose filings go on another docket: briefing status comes from that docket, and the page
    # points readers there for the arguments (unless this case has its own written summaries).
    by_docket = {c["docket"]: c for c in cases}
    for c in cases:
        other = by_docket.get(c["filingsOn"]) if c["filingsOn"] else None
        if c["filingsOn"] and not other:
            flags.append(f"{c['docket']}: filings are on No. {c['filingsOn']}, which isn't tracked.")
        c["filingsOn"] = {"docket": other["docket"], "name": other["name"]} if other else None
        if other:
            c["briefingComplete"] = other["briefingComplete"]
    # Review labels (shown only on the page's #review view): documents Joshua hasn't seen yet.
    for c in cases:
        d, items = c["docket"], []
        if c["qpUrl"] and d not in seen["question"]:
            items.append({"text": "Official question posted", "url": c["qpUrl"]})
        for b in c["meritsBriefs"]:
            if f"{b['date']} {b['kind']}" not in seen["briefs"].get(d, []):
                items.append({"text": f"{b['kind']} filed {fmt(b['date'])}", "url": b["url"]})
        if (c["transcriptUrl"] or c["audioUrl"]) and d not in seen["argument"]:
            what = ("Argument transcript and audio posted" if c["transcriptUrl"] and c["audioUrl"]
                    else "Argument transcript posted" if c["transcriptUrl"] else "Argument audio posted")
            items.append({"text": what, "url": c["transcriptUrl"] or c["audioUrl"]})
        c["review"] = items
        for it in items:
            flags.append(f"{d}: {it['text']}; review it, then add it to data/review_seen.json.")
    for c in cases:
        if c["argued"] and not c["transcriptUrl"]:
            flags.append(f"{c['docket']}: argued, but no transcript link on the Court's transcripts page yet.")
        if c["argued"] and not c["audioUrl"]:
            flags.append(f"{c['docket']}: argued, but no audio link on the Court's audio page yet.")
    unwritten = [c["docket"] for c in cases if not c["content"]]
    if unwritten:
        flags.append(f"{len(unwritten)} case(s) still show \"summary coming soon\".")

    # The first build has nothing to compare with, so it records a launch entry instead of 34 "Added" lines.
    changes = [] if (problems or not prev) else diff(prev, {c["docket"]: c for c in cases}, excluded)
    return cfg, listed, tracked, cases, excluded, changelog, prev_site, problems, flags, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    a = ap.parse_args()
    today = a.today or dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    cfg, listed, tracked, cases, excluded, changelog, prev_site, problems, flags, changes = build(today)

    lines = [f"# Build {today}", ""]
    lines += ["## Changes"] + ([f"- {x}" for x in changes] or ["- No changes."]) + [""]
    if flags:
        lines += ["## Needs your attention"] + [f"- {x}" for x in flags] + [""]
    if problems:
        lines += ["## Problems (nothing was published)"] + [f"- {x}" for x in problems] + [""]
    REPORT.write_text("\n".join(lines))

    # Alert Joshua (by GitHub issue -> email) only for events that need him: a new case, a decision,
    # or a newly posted document to review (emailed once, the first run it appears).
    events = [c for c in changes if c.startswith("Added ") or " was decided on " in c]
    prev_review = {c["docket"]: {i["text"] for i in c.get("review", [])} for c in prev_site.get("cases", [])}
    for c in cases:
        for it in c.get("review", []):
            if c["docket"] in prev_review and it["text"] not in prev_review[c["docket"]]:
                events.append(f"{c['name']}: {it['text']}.")
    if events and not problems:
        NOTIFY.write_text("\n".join(
            ["@jmh11, the Supreme Court Tracker has news that needs your review:", ""]
            + [f"- {e}" for e in events]
            + ["", "New cases need an approved name, tags, question and answer options.",
               "Decided cases need the answer recorded so picks can be scored.",
               "New documents are marked in red on the review view: https://jmh11.github.io/scotus_tracker/#review",
               "", "Full build report: build_report.md in the repository."]))
    print("\n".join(lines))
    if problems:
        return 1

    changelog += [{"date": today, "text": t} for t in changes]
    if not changelog:
        changelog = [{"date": today, "text": f"Tracker launched with {len(cases)} cases."}]
    (DATA / "changelog.json").write_text(json.dumps(changelog, indent=1, ensure_ascii=False) + "\n")
    write_tracked(tracked)
    tagfile = load("tags.json")
    site = {
        "term": cfg["term"], "email": cfg["email"], "repo": cfg["repo"],
        "newGrantCutoff": cfg["newGrantCutoff"], "grantedListAsOf": listed["asOf"],
        "checkedAt": today,
        "updatedAt": today if (changes or not prev_site.get("updatedAt")) else prev_site["updatedAt"],
        "cases": sorted(cases, key=lambda c: c["docket"]),
        "excluded": excluded,
        "tagGroups": [
            {"label": "Kind of question", "tags": tagfile["kinds"]},
            {"label": "Subject", "tags": tagfile["subjects"]},
            {"label": "Court's classification", "tags": ["Civil", "Criminal", "Habeas", "Capital case"]},
        ],
        "changelog": changelog[-25:],
    }
    SITE_DATA.parent.mkdir(exist_ok=True)
    SITE_DATA.write_text(json.dumps(site, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
