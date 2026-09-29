"""Parse state-quota allotment PDFs (Bihar BCECEB PGMAC, Odisha DMET PGMCC) into flat CSVs.

Candidate names, phone numbers and payment refs are deliberately NOT kept.

Usage:  python pipeline/parse_states.py
"""
import csv
import os
import re

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "interim", "states")

FIELDS = ["state", "year", "round", "rank", "state_rank", "candidate_cat", "seat_type", "institute", "course",
          "allotted_cat", "remarks", "status", "candidate_type"]

ROUND_WORDS = {"FIRST": "R1", "SECOND": "R2", "THIRD": "R3", "FOURTH": "R4", "STRAY": "STRAY", "SPECIAL": "SPSTRAY", "MOP": "MOPUP"}


def clean(c):
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


def find_col(header, *names, exclude=()):
    for i, h in enumerate(header):
        hn = h.upper().replace(" ", "").replace("_", "")
        if any(hn == n.upper().replace(" ", "").replace("_", "") for n in names) and i not in exclude:
            return i
    return None


def table_rows(path):
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            for t in page.extract_tables():
                for r in t:
                    yield pno, text, [clean(c) for c in r]


# ---------------------------------------------------------------- Bihar
def parse_bihar(path, year, round_label):
    out, hdr, page_round = [], None, ""
    for pno, text, cells in table_rows(path):
        m = re.search(r"BASIS OF (?:THE )?(\w+)", text.upper())
        if m:
            page_round = ROUND_WORDS.get(m.group(1), m.group(1))
        if any(c.upper().replace(" ", "") in ("INSTITUTE", "INSTITUTENAME", "INSITITUTENAME") for c in cells):
            h = cells
            cols = dict(
                air=find_col(h, "NEET AIR", "AIR"),
                cat=find_col(h, "CATEGORY", "cat", "CATEG ORY", "CAT"),
                seat=find_col(h, "SEAT TYPE", "COURSE TYPE", "K SEAT TYPE"),
                inst=find_col(h, "INSTITUTE", "INSTITUTE NAME", "InstituteName", "INSITITUTE NAME"),
                course=find_col(h, "BRANCH", "BRANCH NAME", "COURSE"),
                acat=find_col(h, "ALLOTTED CAT", "alot_Cat", "ALLOTTED CATEGORY"),
                remark=find_col(h, "REMARK", "ALLOTMENT REMARKS", "Remark", "ALLOTTED REMARKS"),
                urrank=find_col(h, "DEGREE RANK", "Degree_UR_Rank", "STATE DEGREE RANK"),
            )
            cols["status"] = find_col(h, "STATUS", "ALLOT STATUS", "Remarks", exclude=(cols["remark"],))
            hdr = (len(h), cols)
            continue
        if not hdr or len(cells) != hdr[0]:
            continue
        c = hdr[1]
        air = cells[c["air"]].replace(" ", "")
        if not air.isdigit():
            continue
        g = lambda k: cells[c[k]] if c.get(k) is not None else ""
        rnd = round_label or page_round  # 2023 all-rounds file: round comes from the last page title seen
        state_rank = re.search(r"-\s*(\d+)", g("urrank"))
        out.append(dict(state="Bihar", year=year, round=rnd, rank=int(air),
                        state_rank=state_rank.group(1) if state_rank else "",
                        candidate_cat=g("cat"), seat_type=g("seat").title(), institute=g("inst"),
                        course=g("course"), allotted_cat=g("acat"), remarks=g("remark"), status=g("status"),
                        candidate_type=""))
    return out


# ---------------------------------------------------------------- Odisha
def odisha_merit(path):
    """Appln No -> (NEET AIR, category, DIR/INS)"""
    m, hdr = {}, None
    for _, _, cells in table_rows(path):
        if "Appln Number" in cells:
            hdr = (len(cells), cells.index("Appln Number"), cells.index("NEET-AIR"), cells.index("Category"),
                   find_col(cells, "DIR/INS_ Cat", "DIR/INS_Cat", "DIR/INSCat"))
            continue
        if hdr and len(cells) == hdr[0] and cells[hdr[1]].isdigit() and cells[hdr[2]].isdigit():
            m[cells[hdr[1]]] = (int(cells[hdr[2]]), cells[hdr[3]].rstrip(","), cells[hdr[4]] if hdr[4] is not None else "")
    return m


def odisha_cat(c):
    c = c.upper()
    for k, v in (("EWS", "EWS"), ("SEBC", "SEBC"), ("OBC", "SEBC"), ("SC", "SC"), ("ST", "ST"), ("GENERAL", "UR"), ("UR", "UR")):
        if k in c:
            return v
    return c


def parse_odisha(year):
    base = os.path.join(RAW, "odisha", str(year))
    merit = odisha_merit(os.path.join(base, "MERIT.pdf"))
    print(f"  odisha merit list: {len(merit)} candidates")
    # (file, round, appl col, college col, subject col, cat col, course col, status col)
    specs = [("R1.pdf", "R1", "Appli No", "Allotted College", "Allotted Subject", "Allotted Catagory", "Allotted Course", None),
             ("R1_UPG.pdf", "R1_UPGRADE", "Appln No", "Allotted College UGR-1", "Allotted Subject UGR-1",
              "Allotted Category UGR-1", "COURSE", None),
             ("R2.pdf", "R2", "Appl No", "R-2 Allot College", "R-2 Allot Sub", "R-2 Allot Cat", "R-2 Allot Course", None),
             ("FINAL_AFTER_STRAY.pdf", "FINAL_ADMITTED", "Appln No", "Admitted College", "Admitted Subject",
              "Admitted Cat", "Admitted Course", "Admission Status")]
    out = []
    for fname, rnd, *names in specs:
        hdr = None
        for _, _, cells in table_rows(os.path.join(base, fname)):
            if names[0] in cells:
                hdr = (len(cells), [cells.index(n) if n and n in cells else None for n in names],
                       find_col(cells, "Type"))
                continue
            if not hdr or len(cells) != hdr[0]:
                continue
            idx = hdr[1]
            appl = cells[idx[0]]
            if not appl.isdigit() or not cells[idx[1]]:
                continue
            air, cat, ctype = merit.get(appl, ("", "", ""))
            g = lambda i: cells[i] if i is not None else ""
            ctype = g(hdr[2]) or ctype
            out.append(dict(state="Odisha", year=year, round=rnd, rank=air, state_rank="",
                            candidate_cat=odisha_cat(cat), seat_type="Degree", institute=g(idx[1]), course=g(idx[2]),
                            allotted_cat=g(idx[3]), remarks=g(idx[4]), status=g(idx[5]),
                            candidate_type={"DIR": "Direct", "DIRECT": "Direct", "INS": "In-service"}.get(ctype.upper(), ctype)))
        print(f"  odisha {fname}: {sum(1 for r in out if r['round'] == rnd)} rows")
    return out


def write(rows, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    bihar_files = {"2025/R1.pdf": "R1", "2025/R2.pdf": "R2", "2025/R3.pdf": "R3", "2025/STRAY.pdf": "STRAY",
                   "2024/UPTO_R3.pdf": "R3", "2024/STRAY.pdf": "STRAY", "2024/SPSTRAY.pdf": "SPSTRAY",
                   "2023/ALL_ROUNDS.pdf": None}
    rows = []
    for f, rnd in bihar_files.items():
        r = parse_bihar(os.path.join(RAW, "bihar", f), f[:4], rnd)
        print(f"  bihar {f}: {len(r)} rows")
        rows += r
    write(rows, "bihar.csv")
    write(parse_odisha(2025), "odisha.csv")
