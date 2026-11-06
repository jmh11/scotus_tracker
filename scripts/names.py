"""Display names for cases.

Approved names live in data/display_names.json and are used exactly as written.
For a case not in that file, auto_name() turns the Granted & Noted list's all-caps caption
into a readable name with fixed rules. Automatic names are always flagged for review.
"""
import re

# Words kept lower-case unless they start the name.
SMALL = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to"}
# Tokens with a fixed spelling (compared in upper case).
FIXED = {
    "U.S.": "U.S.", "U.S.A.": "U.S.A.", "USA": "USA", "LLC": "LLC", "L.L.C.": "L.L.C.", "INC.": "Inc.",
    "CORP.": "Corp.", "CO.": "Co.", "BD.": "Bd.", "ED.": "Ed.", "DEPT.": "Dept.", "DIST.": "Dist.",
    "ATT'Y": "Att'y", "ATT’Y": "Att’y", "GEN.": "Gen.", "COMM.": "Comm.", "UNIV.": "Univ.",
    "DOGE": "DOGE", "FBI": "FBI", "EPA": "EPA", "FCC": "FCC", "SEC": "SEC", "NLRB": "NLRB",
}


def _word(w: str, first: bool) -> str:
    if w.upper() in FIXED:
        return FIXED[w.upper()]
    if re.fullmatch(r"(?:[A-Z]\.)+", w):      # initials such as "D." or "J.R."
        return w
    if not first and w.lower() in SMALL:
        return w.lower()
    # Capitalize each part of hyphenated or apostrophe words: "O'NEIL" -> "O'Neil"
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), w.lower())


def auto_name(caption_as_listed: str) -> str:
    words = caption_as_listed.split()
    out, first, seen_v = [], True, False
    for w in words:
        if w.upper() == "V." and not seen_v:   # only the first standalone "V." means "versus";
            out.append("v.")                   # later ones are initials, as in "D. V. D."
            seen_v, first = True, True         # the next word starts the second party's name
            continue
        out.append(w if w.upper() == "V." else _word(w, first))
        first = False
    return re.sub(r"\s+,", ",", " ".join(out))


def display_name(docket: str, approved: dict, caption_as_listed: str):
    """Return (name, approved?)."""
    if docket in approved:
        return approved[docket], True
    return auto_name(caption_as_listed), False
