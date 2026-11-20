#!/usr/bin/env python3
"""P-86 gem test: size the handoff-note lines that a fresh session could derive from other sources.

Mechanical part only. It splits each note into sections and content lines, reads the labels written by hand in
p86-labels.json (D derivable, G gem, U unsure) and prints counts, bytes and token estimates.

Usage:
  python3 docs/project/research/p86_gem_test.py              # totals, per-note and per-section tables
  python3 docs/project/research/p86_gem_test.py --check-shas # also run git cat-file on every SHA in D lines
Run from anywhere inside the repository. Python 3.9+, standard library only.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LABELS = os.path.join(HERE, "p86-labels.json")
SECTIONS = ("Goal", "Next action", "State", "What changed", "Decisions", "Constraints",
            "Open questions and blockers", "Dead ends")
KINDS = ("D", "G", "U")


def parse_note(path):
    """Return (total_bytes, [(lineno, section, text, bytes)]) for the content lines of the note."""
    with open(path, "rb") as fh:
        raw = fh.read()
    rows, section = [], None
    for n, line in enumerate(raw.decode("utf-8").split("\n"), 1):
        if n == len(raw.decode("utf-8").split("\n")) and line == "":
            break
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section is None or not line.strip():
            continue
        rows.append((n, section, line, len(line.encode("utf-8")) + 1))
    return len(raw), rows


def load():
    with open(LABELS, encoding="utf-8") as fh:
        data = json.load(fh)
    notes = []
    for rel, spec in data["notes"].items():
        total, rows = parse_note(os.path.join(ROOT, rel))
        labels = spec["lines"]
        seen = set()
        for n, section, text, size in rows:
            if str(n) not in labels:
                raise SystemExit("unlabeled line %s:%d: %s" % (rel, n, text[:60]))
            seen.add(str(n))
        extra = set(labels) - seen
        if extra:
            raise SystemExit("labels for non-content lines in %s: %s" % (rel, sorted(extra, key=int)))
        lines = []
        for n, section, text, size in rows:
            entry = labels[str(n)]
            if entry[0] not in KINDS:
                raise SystemExit("bad label %r at %s:%d" % (entry[0], rel, n))
            lines.append({"n": n, "section": section, "text": text, "bytes": size, "kind": entry[0],
                          "why": entry[1], "mixed": bool(len(entry) > 2 and entry[2])})
        notes.append({"rel": rel, "at": spec.get("at", ""), "bytes": total, "lines": lines})
    return notes


def tally(lines):
    out = {k: [0, 0] for k in KINDS}
    for ln in lines:
        out[ln["kind"]][0] += 1
        out[ln["kind"]][1] += ln["bytes"]
    return out


def pct(a, b):
    return "%.0f%%" % (100.0 * a / b) if b else "-"


def tok(b):
    return int(round(b / 4.0))


def short(rel):
    return re.sub(r"^docs/project/(handoffs/)?", "", rel).replace(".md", "")


def check_shas(notes):
    """Run git cat-file on every SHA and tag named in a D line's note text. Return (checked, missing)."""
    checked, missing = set(), []
    for note in notes:
        for ln in note["lines"]:
            if ln["kind"] != "D":
                continue
            for sha in re.findall(r"\b[0-9a-f]{7,10}\b", ln["text"]):
                if sha in checked or not re.search(r"[0-9]", sha) or not re.search(r"[a-f]", sha):
                    continue
                checked.add(sha)
                r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", sha + "^{commit}"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode != 0:
                    missing.append((note["rel"], ln["n"], sha))
    return len(checked), missing


def duplicates(notes):
    """Content lines that repeat, word for word, a line of an earlier note (notes are in time order)."""
    seen, dup = set(), 0
    dup_bytes = 0
    for note in notes:
        here = set()
        for ln in note["lines"]:
            key = ln["text"].strip()
            if key in seen and not key.startswith("Verify:") and not key.startswith("If it fails:"):
                dup += 1
                dup_bytes += ln["bytes"]
            here.add(key)
        seen |= here
    return dup, dup_bytes


def main(argv):
    notes = load()
    all_lines = [ln for n in notes for ln in n["lines"]]
    tot = tally(all_lines)
    n_lines = len(all_lines)
    n_bytes = sum(v[1] for v in tot.values())
    file_bytes = sum(n["bytes"] for n in notes)

    print("P-86 gem test: %d notes, %d content lines, %d content bytes (%d file bytes)" %
          (len(notes), n_lines, n_bytes, file_bytes))
    print()
    print("Totals (lines, bytes, tokens = bytes/4)")
    for k, name in (("D", "DERIVABLE"), ("G", "GEM"), ("U", "UNSURE")):
        print("  %-9s %4d lines %5s   %6d bytes %5s   ~%d tokens" %
              (name, tot[k][0], pct(tot[k][0], n_lines), tot[k][1], pct(tot[k][1], n_bytes), tok(tot[k][1])))
    mixed = sum(1 for ln in all_lines if ln["mixed"])
    print("  non-D lines that also hold derivable clauses (mixed): %d" % mixed)
    print()
    low = tot["D"][1]
    high = tot["D"][1] + tot["U"][1]
    print("Saving if DERIVABLE lines are dropped (no lost fact): %d bytes, ~%d tokens, %s of content bytes, %s of file bytes" %
          (low, tok(low), pct(low, n_bytes), pct(low, file_bytes)))
    print("Saving if DERIVABLE and UNSURE are dropped (upper bound, loses unsure facts): %d bytes, ~%d tokens, %s of content, %s of file" %
          (high, tok(high), pct(high, n_bytes), pct(high, file_bytes)))
    per_note_after = (file_bytes - low) / float(len(notes))
    print("Average note: %d bytes (~%d tokens) now, %d bytes (~%d tokens) without DERIVABLE lines" %
          (file_bytes / len(notes), tok(file_bytes / len(notes)), per_note_after, tok(per_note_after)))
    dup, dup_bytes = duplicates(notes)
    print("Lines that repeat an earlier note word for word (not Verify/If it fails): %d lines, %d bytes" % (dup, dup_bytes))
    print()

    print("Per note (lines D/G/U, bytes D/G/U, file bytes)")
    print("%-34s %-9s %-15s %-5s" % ("note", "lines", "bytes D/G/U", "file"))
    for n in notes:
        t = tally(n["lines"])
        print("%-34s %2d/%2d/%2d   %4d/%4d/%4d   %5d" % (
            short(n["rel"]), t["D"][0], t["G"][0], t["U"][0], t["D"][1], t["G"][1], t["U"][1], n["bytes"]))
    print()

    print("Per section (lines D/G/U, bytes D/G/U, D share of bytes)")
    print("%-30s %-10s %-17s %s" % ("section", "lines", "bytes D/G/U", "D bytes"))
    for sec in SECTIONS:
        t = tally([ln for ln in all_lines if ln["section"] == sec])
        sb = sum(v[1] for v in t.values())
        print("%-30s %3d/%3d/%3d  %5d/%5d/%5d  %s" % (
            sec, t["D"][0], t["G"][0], t["U"][0], t["D"][1], t["G"][1], t["U"][1], pct(t["D"][1], sb)))

    print()
    print("Next action sub-lines (lines D/G/U, bytes D/G/U)")
    for label, prefix in (("Verify:", "Verify:"), ("If it fails:", "If it fails:")):
        t = tally([ln for ln in all_lines if ln["section"] == "Next action" and ln["text"].startswith(prefix)])
        print("%-30s %3d/%3d/%3d  %5d/%5d/%5d" % (label, t["D"][0], t["G"][0], t["U"][0], t["D"][1], t["G"][1], t["U"][1]))
    t = tally([ln for ln in all_lines if ln["section"] == "Next action" and not ln["text"].startswith(("Verify:", "If it fails:"))])
    print("%-30s %3d/%3d/%3d  %5d/%5d/%5d" % ("action line", t["D"][0], t["G"][0], t["U"][0], t["D"][1], t["G"][1], t["U"][1]))

    if "--check-shas" in argv:
        count, missing = check_shas(notes)
        print()
        print("SHA check on DERIVABLE lines: %d distinct SHAs checked, %d missing" % (count, len(missing)))
        for item in missing:
            print("  missing: %s line %d %s" % item)
        if missing:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
