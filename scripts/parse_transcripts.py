#!/usr/bin/env python3
"""Find each argued case's transcript and audio links on the Court's pages, with fixed rules.

Inputs:  data/raw/argument_transcripts_2026.html, data/raw/argument_audio_2026.html
         (saved unchanged by fetch_raw.py)
Outputs: data/transcripts.json  {docket: transcript PDF address}
         data/audio.json        {docket: audio page address}

Rules:
  transcript  a link whose text is a docket number and whose address is
              "../argument_transcripts/2026/<that docket number>_<code>.pdf"
  audio       a link whose text is a docket number and whose address is exactly
              "../audio/2026/<that docket number>"
A link into those folders whose text and address disagree, or a docket with two different
links, stops the script with an error.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "data" / "raw" / "argument_transcripts_2026.html"
OUT = ROOT / "data" / "transcripts.json"
AUDIO_PAGE = ROOT / "data" / "raw" / "argument_audio_2026.html"
AUDIO_OUT = ROOT / "data" / "audio.json"
AUDIO_LINK_RE = re.compile(r"<a href='(\.\./audio/2026/[^']*)'[^>]*>([^<]*)</a>")
AUDIO_FILE_RE = re.compile(r"^\.\./audio/2026/(\d{2}-\d{1,5})$")
BASE = "https://www.supremecourt.gov/oral_arguments/"

ANY_LINK_RE = re.compile(r"<a href='(\.\./argument_transcripts/2026/[^']+)'[^>]*>([^<]*)</a>")
FILE_RE = re.compile(r"^\.\./argument_transcripts/2026/(\d{2}-\d{1,5})_[A-Za-z0-9]+\.pdf$")
DOCKET_RE = re.compile(r"^\d{2}-\d{1,5}$")


def parse(html: str):
    found, problems = {}, []
    for href, text in ANY_LINK_RE.findall(html):
        text = text.strip()
        m = FILE_RE.match(href)
        if not m or not DOCKET_RE.match(text) or m.group(1) != text:
            problems.append(f"transcript link doesn't fit the rule: {text!r} -> {href!r}")
            continue
        url = BASE + href.removeprefix("../")
        if text in found and found[text] != url:
            problems.append(f"{text} has two different transcripts")
        found[text] = url
    return found, problems


def parse_audio(html: str):
    found, problems = {}, []
    for href, text in AUDIO_LINK_RE.findall(html):
        text = text.strip()
        m = AUDIO_FILE_RE.match(href)
        if not m or not DOCKET_RE.match(text) or m.group(1) != text:
            problems.append(f"audio link doesn't fit the rule: {text!r} -> {href!r}")
            continue
        url = BASE + href.removeprefix("../")
        if text in found and found[text] != url:
            problems.append(f"{text} has two different audio links")
        found[text] = url
    return found, problems


def main() -> int:
    found, problems = parse(PAGE.read_text(encoding="utf-8", errors="replace"))
    audio, audio_problems = parse_audio(AUDIO_PAGE.read_text(encoding="utf-8", errors="replace"))
    for p in problems + audio_problems:
        print(f"PROBLEM {p}")
    if problems or audio_problems:
        return 1
    OUT.write_text(json.dumps(dict(sorted(found.items())), indent=1) + "\n")
    AUDIO_OUT.write_text(json.dumps(dict(sorted(audio.items())), indent=1) + "\n")
    print(f"Transcripts found for {len(found)} case(s); audio found for {len(audio)} case(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
