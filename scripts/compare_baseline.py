#!/usr/bin/env python3
"""One-time check: compare the parsed docket data with the data gathered earlier
with Claude's web-fetch tool (data/baseline_fetch_tool.json). Prints every difference."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
parsed = {r["docket"]: r for r in json.loads((ROOT / "data/parsed_dockets.json").read_text())}
base = {c["docket"]: c for c in json.loads((ROOT / "data/baseline_fetch_tool.json").read_text())["cases"]}

diffs = 0
for d in sorted(set(parsed) | set(base)):
    p, b = parsed.get(d), base.get(d)
    if not p or not b:
        print(f"{d}: only in {'parsed' if p else 'baseline'}"); diffs += 1; continue
    if p["granted"] != b["granted"]:
        print(f"{d}: granted  docket={p['granted']}  earlier={b['granted']}"); diffs += 1
    sched = p["argued"] or p["scheduled"]
    if sched != b["argued"]:
        print(f"{d}: argument docket={sched}  earlier={b['argued']}"); diffs += 1
print(f"\n{len(parsed)} dockets compared, {diffs} difference(s) in grant or argument dates.")
print("\nLower court as the docket states it vs. earlier:")
for d in sorted(parsed):
    if d in base:
        print(f"  {d:<8} {parsed[d]['lowerCourt']:<55} | {base[d]['lowerCourt']}")
