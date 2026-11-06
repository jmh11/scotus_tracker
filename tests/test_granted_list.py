"""Fixed checks for the Granted & Noted list parser."""
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import parse_granted_list as gl  # noqa: E402

# A trimmed copy of the list's real layout, including the consolidated-case and
# same-grant-date patterns that once caused a bug.
SAMPLE = """\
             SUPREME COURT OF THE UNITED STATES
                    GRANTED & NOTED LIST
            OCTOBER TERM 2026 CASES FOR ARGUMENT

                                 As of October 19, 2026

24-1016    CFX   RISEANDSHINE CORP. V. PEPSICO, INC.
                 Court: USCA-2                            Granted: 6/29/26


25-159     CFX   HOFFMANN V. WBI ENERGY TRANSMISSION, INC.
                 Court: USCA-8                      Granted: 6/29/26
                 Argument Date: 11/9/26


25-238)1   CFX   VIRAMONTES V. COOK COUNTY
25-566)2   CFX   GRANT V. HIGGINS
                 Court: 1USCA-7; 2USCA-2                  Granted: 6/30/26
                 Argument Date: 12/2/26

NOTE:
25-886              CFH       GENALO V. BLACK
                              Court: USCA-2 (No. 22-70 only)            Granted: 6/15/26
                              Argument Date: 10/13/26
                              Order: 9/11/26
                              Result: CASE DISMISSED – Rule 46
  2026 TERM CASES FOR ARGUMENT
Total Cases (Arguments) Made Available: 5 (4)
"""


def by_docket(text):
    result, problems = gl.parse(text)
    return {c["docket"]: c for c in result["cases"]}, problems, result


def test_sample_layout():
    cases, problems, result = by_docket(SAMPLE)
    assert not problems
    assert result["asOf"] == "2026-10-19"
    assert cases["24-1016"]["argumentDate"] is None          # must not borrow 25-159's date
    assert cases["25-159"]["argumentDate"] == "2026-11-09"
    assert cases["25-238"]["granted"] == cases["25-566"]["granted"] == "2026-06-30"
    assert cases["25-238"]["argumentDate"] == cases["25-566"]["argumentDate"] == "2026-12-02"
    assert cases["25-886"]["section"] == "note"
    assert cases["25-886"]["result"].startswith("CASE DISMISSED")


def test_total_mismatch_is_an_error():
    _, problems, _ = by_docket(SAMPLE.replace("Made Available: 5", "Made Available: 6"))
    assert any("the list says 6 cases" in p for p in problems)


def test_unexpected_layout_is_an_error():
    broken = SAMPLE.replace("Granted: 6/29/26\n\n\n25-159", "\n\n\n25-159")  # 24-1016 loses its Court/Granted line
    _, problems, _ = by_docket(broken)
    assert problems


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_real_list_parses():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "parse_granted_list.py")],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "35 cases" in out.stdout
