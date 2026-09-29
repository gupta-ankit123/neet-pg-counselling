"""Parse the NMC PG seat matrix (AY 2026-27) -> data/interim/nmc_seat_matrix.csv

Columns: college_code, state, college, category (Govt/Pvt/Deemed), course, seats
"""
import csv
import os
import re

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "nmc", "seat_matrix_2026_27.pdf")
OUT = os.path.join(ROOT, "data", "interim", "nmc_seat_matrix.csv")


def clean(c):
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


def main():
    rows = []
    with pdfplumber.open(SRC) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                for r in t:
                    r = [clean(c) for c in r]
                    if len(r) == 7 and r[0].isdigit() and r[6].isdigit():
                        rows.append(dict(college_code=r[1], state=r[2], college=r[3], category=r[4],
                                         course=r[5], seats=int(r[6])))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} seat-matrix rows, {sum(r['seats'] for r in rows)} seats")


if __name__ == "__main__":
    main()
