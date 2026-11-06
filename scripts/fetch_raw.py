#!/usr/bin/env python3
"""Download raw official files from supremecourt.gov and save them unchanged.

1. The Granted & Noted list  -> data/raw/granted_noted_list.pdf
   The argument transcripts page -> data/raw/argument_transcripts_2026.html
   The argument audio page       -> data/raw/argument_audio_2026.html
2. Docket data for every case that is tracked (data/tracked_dockets.txt) or appears on
   that list                 -> data/raw/dockets/<docket>.json
3. Each case's Questions Presented, as named in its docket -> data/raw/qp/<docket>.pdf

Case numbers are read from the list with the same fixed rules as parse_granted_list.py.
This script does not interpret or change the content of anything it downloads.
Exits with an error if any download fails.
"""
import json
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
TRANSCRIPTS_URL = "https://www.supremecourt.gov/oral_arguments/argument_transcript/2026"
AUDIO_URL = "https://www.supremecourt.gov/oral_arguments/argument_audio/2026"
QP_BASE = "https://www.supremecourt.gov/qp/"


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
    tx = RAW / "argument_transcripts_2026.html"
    print(f"OK    {download(TRANSCRIPTS_URL, tx):>9,} bytes  {tx.relative_to(ROOT)}")
    au = RAW / "argument_audio_2026.html"
    print(f"OK    {download(AUDIO_URL, au):>9,} bytes  {au.relative_to(ROOT)}")
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

    # Each docket names its Questions Presented file in its "QPLink" field ("../qp/25-00170qp.pdf").
    # A file already saved is not downloaded again: the questions presented don't change.
    for d in dockets:
        try:
            qp = json.loads((RAW / "dockets" / f"{d}.json").read_text(encoding="utf-8-sig")).get("QPLink") or ""
        except (OSError, ValueError):
            continue
        if "/qp/" not in qp:
            print(f"NOTE  {d}: docket names no questions-presented file")
            continue
        dest = RAW / "qp" / f"{d}.pdf"
        if dest.exists():
            continue
        try:
            n = download(QP_BASE + qp.split("/qp/")[-1], dest)
            print(f"OK    {n:>9,} bytes  {dest.relative_to(ROOT)}")
        except Exception as e:
            failed.append(f"qp {d}")
            print(f"FAIL  questions presented for {d}: {e}")
        time.sleep(0.5)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
