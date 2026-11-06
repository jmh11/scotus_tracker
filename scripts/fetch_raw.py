#!/usr/bin/env python3
"""Download raw official files from supremecourt.gov and save them unchanged.

1. The Granted & Noted list  -> data/raw/granted_noted_list.pdf
2. Docket data for every case that is tracked (data/tracked_dockets.txt) or appears on
   that list                 -> data/raw/dockets/<docket>.json

Case numbers are read from the list with the same fixed rules as parse_granted_list.py.
This script does not interpret or change the content of anything it downloads.
Exits with an error if any download fails.
"""
import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import parse_granted_list as gl  # noqa: E402
from tracked import read_tracked  # noqa: E402

UA = "scotus-tracker/0.1 (+https://github.com/jmh11/scotus_tracker)"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DOCKET_URL = "https://www.supremecourt.gov/RSS/Cases/JSON/{}.json"
GRANTED_URL = "https://www.supremecourt.gov/orders/26grantednotedlist.pdf"


def download(url: str, dest: pathlib.Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return len(body)


def main() -> int:
    pdf = RAW / "granted_noted_list.pdf"
    print(f"OK    {download(GRANTED_URL, pdf):>9,} bytes  {pdf.relative_to(ROOT)}")
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          capture_output=True, text=True).stdout
    listed, problems = gl.parse(text)
    if problems:
        for p in problems:
            print(f"PROBLEM granted list: {p}")
        return 1
    dockets = sorted(set(read_tracked()) | {c["docket"] for c in listed["cases"]})
    failed = []
    for d in dockets:
        dest = RAW / "dockets" / f"{d}.json"
        try:
            n = download(DOCKET_URL.format(d), dest)
            print(f"OK    {n:>9,} bytes  {dest.relative_to(ROOT)}")
        except Exception as e:
            failed.append(d)
            print(f"FAIL  {d}: {e}")
        time.sleep(0.5)  # be polite to the Court's server
    print(f"\nGranted list plus {len(dockets) - len(failed)} of {len(dockets)} docket files downloaded.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
