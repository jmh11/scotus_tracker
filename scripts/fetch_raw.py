#!/usr/bin/env python3
"""Download raw official files from supremecourt.gov and save them unchanged.

Reads docket numbers from data/tracked_dockets.txt. Saves:
  data/raw/dockets/<docket>.json   the Court's structured docket data, byte for byte
  data/raw/granted_noted_list.pdf  the Granted & Noted list, byte for byte

This script does not read, interpret or change the content of anything it downloads.
Exits with an error if any download fails.
"""
import pathlib
import sys
import time
import urllib.request

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
    dockets = [d.strip() for d in (ROOT / "data" / "tracked_dockets.txt").read_text().splitlines() if d.strip()]
    failed = []
    jobs = [(DOCKET_URL.format(d), RAW / "dockets" / f"{d}.json") for d in dockets]
    jobs.append((GRANTED_URL, RAW / "granted_noted_list.pdf"))
    for url, dest in jobs:
        try:
            n = download(url, dest)
            print(f"OK    {n:>9,} bytes  {dest.relative_to(ROOT)}")
        except Exception as e:
            failed.append(url)
            print(f"FAIL  {url}: {e}")
        time.sleep(0.5)  # be polite to the Court's server
    print(f"\n{len(jobs) - len(failed)} of {len(jobs)} downloads succeeded.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
