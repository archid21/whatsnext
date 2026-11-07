# Plan

One line per item: `- [ ] P-N Title · done means: <how we know it is done>`.

## Next
- [ ] P-1 Create project structure per implementation plan · done means: `python3 -m unittest discover -s tests` passes
- [x] P-2 Configure linting and formatting tools · done means: `python3 -m unittest discover -s tests` passes · evidence: unverified
- [ ] P-3 Contract test for `report --csv` · done means: `python3 -m unittest tests.contract.test_csv` passes
- [ ] P-4 Create the row formatter in src/csvfmt.py · done means: `python3 -m unittest discover -s tests` passes
- [ ] P-5 Wire `--csv` into src/cli.py · done means: `python3 -m unittest discover -s tests` passes · blocked by: P-4
- [ ] P-6 Documentation updates in docs/ · done means: `python3 -m unittest discover -s tests` passes
