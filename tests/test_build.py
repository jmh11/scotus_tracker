"""Fixed checks for build.py: new grants, the cutoff, dismissals and the change log."""
import json
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import tracked  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A copy of data/ and site/ so tests never touch the real files."""
    shutil.copytree(ROOT / "data", tmp_path / "data", ignore=shutil.ignore_patterns("raw", "samples"))
    (tmp_path / "site").mkdir()
    monkeypatch.setattr(build, "DATA", tmp_path / "data")
    monkeypatch.setattr(build, "SITE_DATA", tmp_path / "site" / "cases.json")
    monkeypatch.setattr(build, "REPORT", tmp_path / "build_report.md")
    monkeypatch.setattr(tracked, "PATH", tmp_path / "data" / "tracked_dockets.txt")
    monkeypatch.setattr(build, "read_tracked", lambda: tracked.read_tracked(tmp_path / "data" / "tracked_dockets.txt"))
    monkeypatch.setattr(build, "write_tracked", lambda t: tracked.write_tracked(t, tmp_path / "data" / "tracked_dockets.txt"))
    return tmp_path


def edit(path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def test_current_data_builds_cleanly(sandbox):
    _, listed, tracked, cases, excluded, _, _, problems, _, _ = build.build("2026-11-06")
    assert not problems
    # Every case the list shows for argument (up to the cutoff) is on the page, plus the 34 launch cases.
    for_argument = {c["docket"] for c in listed["cases"] if c["section"] == "for argument"}
    assert for_argument <= {c["docket"] for c in cases}
    assert len(cases) >= 34


def test_change_log_and_new_grant_rules(sandbox):
    d = sandbox / "data"
    # First build: no previous page, so no change lines.
    first = build.build("2026-11-06")
    assert first[-1] == []
    site = {"cases": first[3], "updatedAt": "2026-11-06"}
    (sandbox / "site" / "cases.json").write_text(json.dumps(site))

    def change(data):
        for r in data:
            if r["docket"] == "25-170":
                r.update(decided="2027-03-01", outcome="reverse")
            if r["docket"] == "25-1103":
                r.update(scheduled="2027-02-23")
        data.append({**data[0], "docket": "26-999", "granted": "2026-11-16", "argued": None,
                     "scheduled": None, "decided": None, "outcome": None})
    edit(d / "parsed_dockets.json", change)

    def add_grants(g):
        g["cases"].append({"docket": "26-999", "group": None, "code": "CFX", "captionAsListed": "TEST V. CASE",
                           "section": "for argument", "courtCodes": "USCA-2", "granted": "2026-11-16",
                           "argumentDate": None, "result": None})
        g["cases"].append({"docket": "26-998", "group": None, "code": "CFX", "captionAsListed": "LATE V. GRANT",
                           "section": "for argument", "courtCodes": "USCA-2", "granted": "2027-02-02",
                           "argumentDate": None, "result": None})
    edit(d / "granted_list.json", add_grants)

    _, _, trk, cases, _, _, _, problems, flags, changes = build.build("2026-11-16")
    assert not problems
    assert trk["26-999"] == "2026-11-16" and "26-998" not in trk
    assert any("Added Test v. Case (No. 26-999)" in c for c in changes)
    assert any("was decided on Mar 1, 2027: reversed" in c for c in changes)
    assert any("argument scheduled for Feb 23, 2027" in c for c in changes)
    assert any("26-998" in f and "cutoff" in f for f in flags)
    assert any("26-999" in f and "needs your approval" in f for f in flags)


def test_grant_date_disagreement_stops_the_build(sandbox):
    edit(sandbox / "data" / "granted_list.json",
         lambda g: next(c for c in g["cases"] if c["docket"] == "25-170").update(granted="2026-02-24"))
    problems = build.build("2026-11-06")[7]
    assert any("25-170: grant date" in p for p in problems)


def test_unknown_court_stops_the_build(sandbox):
    edit(sandbox / "data" / "court_names.json", lambda t: t.pop("Supreme Court of Colorado"))
    problems = build.build("2026-11-06")[7]
    assert any("court_names.json" in p for p in problems)


def test_unknown_tag_stops_the_build(sandbox):
    edit(sandbox / "data" / "tags.json", lambda t: t["cases"]["25-170"]["subjects"].append("Climate"))
    problems = build.build("2026-11-06")[7]
    assert any("'Climate' is not in the subjects list" in p for p in problems)


def test_court_classification_tags(sandbox):
    cases = {c["docket"]: c for c in build.build("2026-11-06")[3]}
    assert cases["25-1003"]["tags"]["court"] == ["Habeas", "Capital case"]
    assert cases["25-5343"]["tags"]["court"] == ["Criminal"]
    assert cases["25-238"]["tags"]["court"] == ["Civil"]


def test_answer_options_are_checked(sandbox):
    edit(sandbox / "data" / "content.json", lambda c: c["25-170"]["options"].append(dict(c["25-170"]["options"][0])))
    problems = build.build("2026-11-06")[7]
    assert any("25-170" in p and "unique id" in p for p in problems)


def test_third_side_needs_a_heading(sandbox):
    edit(sandbox / "data" / "content.json", lambda c: c["25-170"].update(amicus="Some argument."))
    problems = build.build("2026-11-06")[7]
    assert any("25-170" in p and "amicusHeading" in p for p in problems)
    edit(sandbox / "data" / "content.json", lambda c: c["25-170"].update(amicusHeading="Court-appointed lawyer's argument"))
    assert not build.build("2026-11-06")[7]


def test_recorded_result_must_match_an_option(sandbox):
    (sandbox / "data" / "results.json").write_text('{"25-735": "maybe"}')
    problems = build.build("2026-11-06")[7]
    assert any("25-735" in p for p in problems)   # not an option, and the case isn't decided yet


def test_decided_case_without_result_is_flagged(sandbox):
    edit(sandbox / "data" / "parsed_dockets.json",
         lambda rs: next(r for r in rs if r["docket"] == "25-735").update(decided="2027-03-01", outcome="reverse"))
    _, _, _, cases, _, _, _, problems, flags, _ = build.build("2026-11-06")
    assert not problems
    assert any("25-735" in f and "results.json" in f for f in flags)
    assert next(c for c in cases if c["docket"] == "25-735")["result"] is None


def test_unreviewed_documents_get_review_labels(sandbox):
    def forget(seen):
        # Start from "everything reviewed", so documents filed since the data was saved don't affect the test.
        recs = json.loads((sandbox / "data" / "parsed_dockets.json").read_text())
        seen["question"] = [r["docket"] for r in recs]
        seen["argument"] = [r["docket"] for r in recs]
        seen["briefs"] = {r["docket"]: [f"{b['date']} {b['kind']}" for b in r["meritsBriefs"]] for r in recs}
        seen["question"].remove("25-170")
        seen["briefs"]["25-170"] = []
        seen["argument"].remove("25-170")
    edit(sandbox / "data" / "review_seen.json", forget)
    _, _, _, cases, _, _, _, problems, flags, _ = build.build("2026-11-06")
    assert not problems
    labels = [r["text"] for r in next(c for c in cases if c["docket"] == "25-170")["review"]]
    assert "Official question posted" in labels
    assert "Petitioner's brief filed May 14, 2026" in labels
    assert any(l.startswith("Argument transcript") for l in labels)
    assert all(not c["review"] for c in cases if c["docket"] != "25-170")
