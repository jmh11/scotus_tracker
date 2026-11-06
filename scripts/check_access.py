#!/usr/bin/env python3
"""Connectivity test: can this machine download the official files the tracker needs?

Downloads each file once, prints the HTTP status and size, and exits with an error
if any download fails. It reads nothing and changes nothing.
"""
import sys
import urllib.request

UA = "scotus-tracker/0.1 (+https://github.com/jmh11/scotus_tracker)"
URLS = {
    "Granted & Noted list (PDF)": "https://www.supremecourt.gov/orders/26grantednotedlist.pdf",
    "Docket data for 25-170 (JSON)": "https://www.supremecourt.gov/RSS/Cases/JSON/25-170.json",
    "Orders of the Court, 2026": "https://www.supremecourt.gov/orders/ordersofthecourt/26",
    "Argument calendars page": "https://www.supremecourt.gov/oral_arguments/calendarsandlists.aspx",
    "Opinions page, 2026 term": "https://www.supremecourt.gov/opinions/slipopinion/26",
}

failed = 0
for name, url in URLS.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            print(f"OK    {r.status}  {len(body):>9,} bytes  {r.headers.get('Content-Type','?'):<30}  {name}")
    except Exception as e:  # report every failure, keep going
        failed += 1
        print(f"FAIL  {name}: {e}")

print(f"\n{len(URLS) - failed} of {len(URLS)} downloads succeeded.")
sys.exit(1 if failed else 0)
