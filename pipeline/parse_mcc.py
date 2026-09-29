"""Parse MCC NEET-PG allotment result PDFs into flat CSVs.

Every data row is anchored from the right: the round being published is always the
last block of 7 cells (quota, institute, course, allotted cat, candidate cat, option no,
remarks) — or 6 cells for single-round files (R1, stray) which have no option number.
Earlier rounds appear as 4-cell "trail" blocks (quota, institute, course, status).

Usage:  python pipeline/parse_mcc.py            (parses every PDF under data/raw/mcc)
"""
import csv
import glob
import os
import re
import sys
from multiprocessing import Pool

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "mcc")
OUT = os.path.join(ROOT, "data", "interim", "mcc")

# file key -> (round label, number of rounds shown in the file)
FILE_ROUNDS = {"R1": ("R1", 1), "R2": ("R2", 2), "R3": ("R3", 3), "STRAY": ("STRAY", 1), "SPSTRAY": ("SPSTRAY", 1)}
CHUNK = 60

FIELDS = ["year", "round", "rank", "quota", "institute", "course", "allotted_cat", "candidate_cat",
          "option_no", "remarks", "prev1_quota", "prev1_institute", "prev1_course", "prev1_status",
          "prev2_quota", "prev2_institute", "prev2_course", "prev2_status", "page"]


def clean(c):
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


def parse_row(cells, n_rounds):
    """Return dict for a data row, or None if it isn't one."""
    tail = 6 if n_rounds == 1 else 7
    for variant in (cells, [c for c in cells if c != ""]):
        for off in (1, 2):
            if len(variant) != off + 4 * (n_rounds - 1) + tail:
                continue
            rank = variant[off - 1].replace(" ", "")
            if not rank.isdigit():
                continue
            rec = {"rank": int(rank)}
            pos = off
            trails = []
            for _ in range(n_rounds - 1):
                trails.append(variant[pos:pos + 4])
                pos += 4
            sec = variant[pos:]
            if tail == 6:
                sec = sec[:5] + [""] + sec[5:]
            (rec["quota"], rec["institute"], rec["course"], rec["allotted_cat"],
             rec["candidate_cat"], rec["option_no"], rec["remarks"]) = sec
            # prev1 = the round immediately before this one, prev2 = the one before that
            for i, t in enumerate(reversed(trails), start=1):
                rec[f"prev{i}_quota"], rec[f"prev{i}_institute"], rec[f"prev{i}_course"], rec[f"prev{i}_status"] = t
            return rec
    return None


def parse_chunk(args):
    path, start, end, n_rounds = args
    rows, skipped = [], 0
    with pdfplumber.open(path) as pdf:
        for i in range(start, end):
            for table in pdf.pages[i].extract_tables():
                for raw in table:
                    cells = [clean(c) for c in raw]
                    rec = parse_row(cells, n_rounds)
                    if rec:
                        rec["page"] = i + 1
                        rows.append(rec)
                    elif cells and cells[-1] and any(ch.isdigit() for ch in "".join(cells[:2])):
                        skipped += 1
    return rows, skipped


def parse_file(pool, path):
    year = os.path.basename(os.path.dirname(path))
    key = os.path.splitext(os.path.basename(path))[0]
    label, n_rounds = FILE_ROUNDS[key]
    out = os.path.join(OUT, f"{year}_{key}.csv")
    if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(path):
        print("skip (up to date)", out)
        return
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
    jobs = [(path, s, min(s + CHUNK, n), n_rounds) for s in range(0, n, CHUNK)]
    rows, skipped = [], 0
    for r, s in pool.imap(parse_chunk, jobs):
        rows += r
        skipped += s
    os.makedirs(OUT, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            r.update(year=year, round=label)
            w.writerow({k: r.get(k, "") for k in FIELDS})
    print(f"{year} {key}: {n} pages -> {len(rows)} rows ({skipped} unparsed candidate rows)", flush=True)


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(p for p in glob.glob(os.path.join(RAW, "*", "*.pdf"))
                                   if os.path.splitext(os.path.basename(p))[0] in FILE_ROUNDS)
    with Pool(max(1, os.cpu_count() - 1)) as pool:
        for p in files:
            parse_file(pool, p)
