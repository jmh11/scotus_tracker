# Supreme Court Tracker

A page for tracking the Supreme Court's argued cases this term and recording what the Court
*should* and *will* do. Live at https://jmh11.github.io/scotus_tracker/

## How the page is updated

Everything runs as fixed code on GitHub Actions ("Update and publish" workflow). No AI is used
to read or interpret the Court's documents.

1. **Download** (`scripts/fetch_raw.py`): the Granted & Noted list and each case's docket data,
   straight from supremecourt.gov, saved unchanged in `data/raw/`.
2. **Read the list** (`scripts/parse_granted_list.py`): fixed layout rules; the count must match
   the list's own stated total.
3. **Read the dockets** (`scripts/parse_dockets.py`): grant, argument and decision facts from the
   Court's own docket entries, using exact wording patterns.
4. **Test** (`tests/`): the rules are checked against real dockets from this term and last term.
5. **Build** (`scripts/build.py`): combines the facts with the approved files below, runs
   cross-checks, and writes `site/cases.json` and `build_report.md`.
6. **Publish**: the `site/` folder goes to GitHub Pages.

Any failed step stops the run and nothing is published.

## Files only Joshua approves

- `data/display_names.json`: case names shown on the page
- `data/content.json`: case summaries and what each outcome would mean
- `data/court_names.json`: short forms of lower-court names
- `data/config.json`: term, new-grant cutoff (Jan 31, 2027), contact email
