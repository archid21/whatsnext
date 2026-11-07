# Story 1.1: Row formatter

Status: ready-for-dev

## Story

As a report reader,
I want rows turned into CSV lines,
so that I can open them in a spreadsheet.

## Acceptance Criteria

1. A row with a comma in a value is quoted.
2. A row with a quote in a value doubles the quote.

## Tasks / Subtasks

- [ ] Task 1: Write the formatter (AC: 1, 2)
  - [ ] Create `src/csvfmt.py` with `format_row`
  - [ ] Add tests in `tests/test_csvfmt.py`

## Dev Notes

Run `python3 -m unittest tests.test_csvfmt` before marking the story done.
