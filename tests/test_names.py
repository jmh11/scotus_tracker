"""Fixed checks for automatic display names."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from names import auto_name, display_name  # noqa: E402


def test_auto_names():
    assert auto_name("DEPARTMENT OF HOMELAND SECURITY V. D. V. D.") == "Department of Homeland Security v. D. V. D."
    assert auto_name("ASSOCIATION FOR EDUCATION FAIRNESS V. MONTGOMERY COUNTY BD. OF ED.") == \
        "Association for Education Fairness v. Montgomery County Bd. of Ed."
    assert auto_name("SUNCOR ENERGY (U.S.A.) INC. V. COMMISSIONERS OF BOULDER COUNTY") == \
        "Suncor Energy (U.S.A.) Inc. v. Commissioners of Boulder County"
    assert auto_name("U.S. DOGE SERVICE V. UNITED STATES DIST. COURT FOR D. C.") == \
        "U.S. DOGE Service v. United States Dist. Court for D. C."


def test_approved_name_wins():
    assert display_name("1-1", {"1-1": "Approved v. Name"}, "OTHER V. NAME") == ("Approved v. Name", True)
    assert display_name("1-2", {}, "OTHER V. NAME") == ("Other v. Name", False)


def test_usa_stays_capitalized():
    assert auto_name("GOLDMAN SACHS BANK USA V. BROWN") == "Goldman Sachs Bank USA v. Brown"
