"""Parse a counselling PDF uploaded in the app (e.g. MCC 2026 Round 1 result) into the allotments schema."""
import os
import re
import tempfile
from collections import Counter

import pandas as pd
import pdfplumber

from core.mcc import apply_institute_map, normalize_mcc
from core.normalize import QUOTA_MAP, quota_of
from pipeline.build import finish_state, load_bihar
from pipeline.parse_mcc import clean, parse_row
from pipeline.parse_states import parse_bihar

KNOWN_QUOTAS = {v[0] for v in QUOTA_MAP.values()} | {"ESI"}


def _detect(pdf):
    """-> ('mcc', n_rounds) | ('bihar', None) | ('table', None)"""
    votes = Counter()
    for page in pdf.pages[1:min(len(pdf.pages), 8)]:
        text = (page.extract_text() or "").upper()
        if "PGMAC" in text or "BCECE" in text:
            return "bihar", None
        for t in page.extract_tables():
            for r in t:
                cells = [clean(c) for c in r]
                for n in (1, 2, 3, 4):
                    rec = parse_row(cells, n)
                    if rec and quota_of(rec["quota"])[0] in KNOWN_QUOTAS | {"-"}:
                        votes[n] += 1
    if votes:
        return "mcc", votes.most_common(1)[0][0]
    return "table", None


def _generic_tables(pdf, progress=None):
    rows, header = [], None
    for i, page in enumerate(pdf.pages):
        for t in page.extract_tables():
            for r in t:
                cells = [clean(c) for c in r]
                if header is None and sum(bool(c) for c in cells) >= 3:
                    header = cells
                    continue
                if header and len(cells) == len(header) and cells != header:
                    rows.append(cells)
        if progress:
            progress((i + 1) / len(pdf.pages))
    if not header:
        return pd.DataFrame()
    cols = [h or f"col{i}" for i, h in enumerate(header)]
    cols = [c if cols.count(c) == 1 else f"{c}_{i}" for i, c in enumerate(cols)]
    return pd.DataFrame(rows, columns=cols)


def parse_upload(data: bytes, year: int, round_label: str = "", progress=None, institute_map=None):
    """-> (kind, DataFrame). kind: 'mcc' (normalised allotments), 'bihar' (normalised) or 'table' (raw)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        with pdfplumber.open(path) as pdf:
            kind, n_rounds = _detect(pdf)
            if kind == "mcc":
                rows = []
                for i, page in enumerate(pdf.pages):
                    for t in page.extract_tables():
                        for r in t:
                            rec = parse_row([clean(c) for c in r], n_rounds)
                            if rec:
                                rows.append(rec)
                    if progress:
                        progress((i + 1) / len(pdf.pages))
                raw = pd.DataFrame(rows).fillna("")
                label = round_label or (f"R{n_rounds}" if n_rounds > 1 else "R1")
                raw["year"], raw["round"] = year, label
                for c in ("option_no", "prev1_quota", "prev1_institute", "prev1_course", "prev1_status"):
                    if c not in raw:
                        raw[c] = ""
                return "mcc", apply_institute_map(normalize_mcc(raw), institute_map)
            if kind == "bihar":
                rows = parse_bihar(path, year, round_label or "R1")
                d = finish_state(load_bihar(pd.DataFrame(rows)), "Bihar")
                d["round_label"] = d["round"]
                return "bihar", d
            return "table", _generic_tables(pdf, progress)
    finally:
        os.unlink(path)


def compare_with_history(new: pd.DataFrame, closing: pd.DataFrame, round_no: float):
    """Closing rank of each seat group in the uploaded round vs the same round in earlier years."""
    keys = ["quota_name", "institute", "inst_state", "college_type", "branch", "degree", "allotted_cat", "allotted_pwd"]
    cur = new.groupby(keys, dropna=False)["rank"].agg(opening="min", closing_now="max", allotted_now="size").reset_index()
    hist = closing[(closing["counselling"] == "MCC (All India)") & (closing["round_no"] == round_no)]
    for y in sorted(hist["year"].unique(), reverse=True):
        h = hist[hist["year"] == y].groupby(keys, dropna=False)["closing"].max().rename(f"closing_{y}").reset_index()
        cur = cur.merge(h, on=keys, how="left")
    last = [c for c in cur.columns if re.match(r"closing_\d{4}", c)]
    if last:
        cur["change_vs_last_year"] = cur["closing_now"] - cur[last[0]]
        cur["change_%"] = (100 * cur["change_vs_last_year"] / cur[last[0]]).round(1)
    return cur.sort_values("closing_now")
