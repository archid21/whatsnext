# CSV Export Implementation Plan

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a report as CSV.
**Architecture:** one formatter module, one CLI flag.
**Tech Stack:** Python 3.9, unittest.

---

### Task 1: Row formatter

**Files:**
- Create: `src/csvfmt.py`
- Test: `tests/test_csvfmt.py`

**Interfaces:** Produces `format_row(values) -> str`.

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
  Run: `python3 -m unittest tests.test_csvfmt`
  Expected: FAIL
- [ ] **Step 3: Implement `format_row`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `python3 -m unittest tests.test_csvfmt`
  Expected: PASS
- [ ] **Step 5: Commit**

### Task 2: `--csv` flag

**Files:**
- Modify: `src/cli.py:10-40`
- Test: `tests/test_cli.py`

**Interfaces:** Consumes `format_row` from Task 1.

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Implement the flag**
- [ ] **Step 3: Run test to verify it passes**
  Run: `python3 -m unittest tests.test_cli`
  Expected: PASS

### Task 3: Document the flag

**Files:**
- Modify: `README.md`

- [x] **Step 1: Add a usage example**
