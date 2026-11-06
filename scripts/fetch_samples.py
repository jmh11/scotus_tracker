#!/usr/bin/env python3
"""Development only: download last term's decided cases so the decision rules can be
written and tested against real docket entries.

Saves, unchanged:
  data/samples/ot2025/slipopinion_25.html     the Court's opinions page for the 2025 term
  data/samples/ot2025/dockets/<docket>.json   docket data for every case number on that page

Case numbers are taken from the page with one fixed pattern (NN-NNNN). Nothing here is used
by the live pipeline.
"""
import pathlib
import re
import sys
import time
import urllib.request

UA = "scotus-tracker/0.1 (+https://github.com/jmh11/scotus_tracker)"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "samples" / "ot2025"
PAGE = "https://www.supremecourt.gov/opinions/slipopinion/25"
DOCKET_URL = "https://www.supremecourt.gov/RSS/Cases/JSON/{}.json"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    html = get(PAGE)
    (OUT / "slipopinion_25.html").write_bytes(html)
    dockets = sorted(set(re.findall(r"\b(\d{2}-\d{1,5})\b", html.decode("utf-8", "replace"))))
    print(f"Opinions page saved; {len(dockets)} case numbers found on it.")
    failed = 0
    for d in dockets:
        try:
            body = get(DOCKET_URL.format(d))
            (OUT / "dockets").mkdir(exist_ok=True)
            (OUT / "dockets" / f"{d}.json").write_bytes(body)
        except Exception as e:
            failed += 1
            print(f"FAIL  {d}: {e}")
        time.sleep(0.5)
    print(f"{len(dockets) - failed} of {len(dockets)} docket files saved.")
    return 1 if failed > len(dockets) // 4 else 0


if __name__ == "__main__":
    sys.exit(main())
