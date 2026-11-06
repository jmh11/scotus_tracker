"""The list of tracked cases: data/tracked_dockets.txt.

One case per line: "<docket>" or "<docket> <date added>" (YYYY-MM-DD). The 34 launch cases
have no date, so they never show a "New" tag. Only build.py adds lines, and only for cases
the Granted & Noted list shows as granted on or before the new-grant cutoff.
"""
import pathlib
import re

PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "tracked_dockets.txt"
LINE_RE = re.compile(r"^(\d{2}-\d{1,5})(?:\s+(\d{4}-\d{2}-\d{2}))?$")


def read_tracked(path: pathlib.Path = PATH) -> dict:
    """Return {docket: date added or None}. Raises ValueError on a malformed line."""
    out = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        m = LINE_RE.match(line.strip())
        if not m:
            raise ValueError(f"{path.name} line {n} is malformed: {line!r}")
        out[m.group(1)] = m.group(2)
    return out


def write_tracked(tracked: dict, path: pathlib.Path = PATH) -> None:
    def key(d):
        a, b = d.split("-")
        return (int(a), int(b))
    lines = [d if tracked[d] is None else f"{d} {tracked[d]}" for d in sorted(tracked, key=key)]
    path.write_text("\n".join(lines) + "\n")
