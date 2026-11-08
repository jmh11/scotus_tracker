"""Fixed checks for the docket parser, run against real dockets saved in the repository.

These lock in the parser's behavior: any change to the rules that alters a result here
makes the tests fail, so rule changes can't slip in unnoticed.
Run: python -m pytest -q
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import parse_dockets as pd  # noqa: E402

SAMPLES = ROOT / "data" / "samples" / "ot2025" / "dockets"


def parsed(docket: str, folder=SAMPLES):
    rec, problems = pd.parse(folder / f"{docket}.json")
    return rec, problems


def test_every_argued_sample_case_has_a_decision():
    argued = 0
    for path in SAMPLES.glob("*.json"):
        rec, problems = pd.parse(path)
        if rec["argued"]:
            argued += 1
            assert not problems, (rec["docket"], problems)
            assert rec["decided"] and rec["outcome"] and rec["opinionUrl"], rec["docket"]
    assert argued == 56


def test_outcomes_on_known_cases():
    expected = {
        "24-1021": "reverse",    # consolidated; the other docket's AFFIRMED clause must not count here
        "24-1287": "vacate",     # consolidated; "No. 24-1287 is VACATED ...; No. 25-250 is AFFIRMED"
        "24-5774": "mixed",      # REVERSED IN PART
        "24-872": "dismissed",   # dismissed as improvidently granted
        "24-109": "affirm",      # reargued case
    }
    for docket, outcome in expected.items():
        rec, problems = parsed(docket)
        assert rec["outcome"] == outcome, (docket, rec["outcome"], rec["judgmentText"])


def test_grant_variants():
    assert parsed("23-1209")[0]["granted"] == "2025-06-30"   # later amended grant order is ignored
    assert parsed("25-1083")[0]["granted"] == "2026-03-16"   # stay application treated as a petition
    assert parsed("25-5146")[0]["granted"] == "2025-12-05"   # "The petition ... is GRANTED"


def test_reargued_case_keeps_latest_argument():
    rec, _ = parsed("24-109")
    assert rec["reargued"] and rec["argued"] == "2025-10-15"


def test_capital_case_number_is_cleaned():
    rec, problems = parsed("25-1003", ROOT / "data" / "raw" / "dockets")
    assert rec["docket"] == "25-1003" and rec["capitalCase"] and not problems


def test_live_dockets_parse_without_problems():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "parse_dockets.py"),
                          str(ROOT / "data" / "raw" / "dockets"), "/tmp/parsed_test.json"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_merits_briefs_skip_petition_stage_and_amici():
    rec, _ = parsed("25-170", ROOT / "data" / "raw" / "dockets")
    kinds = [b["kind"] for b in rec["meritsBriefs"]]
    assert kinds[:3] == ["Petitioner's brief", "Respondent's brief", "Petitioner's reply brief"]
    assert all(b["date"] > rec["granted"] for b in rec["meritsBriefs"])


def test_merits_briefs_with_unusual_titles():
    live = ROOT / "data" / "raw" / "dockets"
    # "Brief for the respondent ... supporting vacatur filed", plus a Court-appointed lawyer's brief.
    kinds = [b["kind"] for b in parsed("25-5930", live)[0]["meritsBriefs"]]
    assert "Respondent's brief" in kinds and "Court-appointed amicus brief" in kinds
    # "Brief for the petitioners filed."
    assert "Petitioner's brief" in [b["kind"] for b in parsed("26-426", live)[0]["meritsBriefs"]]
    # "Brief of Court-appointed amicus curiae filed."; ordinary amicus briefs still don't count.
    kinds = [b["kind"] for b in parsed("25-5343", live)[0]["meritsBriefs"]]
    assert kinds.count("Court-appointed amicus brief") == 1 and len(kinds) == 5


def test_consolidated_filings_docket():
    live = ROOT / "data" / "raw" / "dockets"
    assert parsed("25-566", live)[0]["filingsOn"] == "25-238"   # filings moved to the other docket
    assert parsed("25-238", live)[0]["filingsOn"] is None       # the docket that holds them
    assert parsed("25-170", live)[0]["filingsOn"] is None       # not consolidated
