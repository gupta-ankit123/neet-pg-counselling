"""Merge parsed MCC + state CSVs into clean parquet tables used by the app.

Outputs (data/processed/):
  allotments.parquet   one row per allotment (all counsellings / years / rounds)
  closing.parquet      opening/closing rank per seat group per round
  journeys.parquet     MCC candidate journey R1 -> R2 -> R3 -> stray, by rank
  seat_matrix_2026.parquet  NMC 2026-27 seats with branch / college type
"""
import glob
import os
import re
import sys

import pandas as pd
import pdfplumber
from rapidfuzz import fuzz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.mcc import ROUND_LABEL, ROUND_NO, closing_ranks, normalize_mcc  # noqa: E402
from core.normalize import (STATES, branch_of, category_of, clean_remark, clean_status, degree_of, institute_name,  # noqa: E402
                            name_key, quota_of, state_of, undouble)

INTERIM = os.path.join(ROOT, "data", "interim")
OUT = os.path.join(ROOT, "data", "processed")


# ---------------------------------------------------------------------------------------------- MCC
def mcc_code_names():
    """Course abbreviations (GMED -> M.D. (GENERAL MEDICINE)) listed on the first pages of MCC 2025 R3."""
    codes = {}
    path = os.path.join(ROOT, "data", "raw", "mcc", "2025", "R3.pdf")
    if os.path.exists(path):
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:4]:
                for line in (page.extract_text() or "").splitlines():
                    m = re.match(r"^([A-Z][A-Z\-]{2,6})\s+(.{4,})$", line.strip())
                    if m and m.group(1) not in ("NEET",):
                        codes[m.group(1)] = m.group(2)
    return codes


def load_mcc():
    frames = [pd.read_csv(f, dtype=str, keep_default_na=False)
              for f in sorted(glob.glob(os.path.join(INTERIM, "mcc", "*.csv")))]
    raw = pd.concat(frames, ignore_index=True)
    raw["year"] = raw["year"].astype(int)
    raw["rank"] = raw["rank"].astype(int)
    return raw, normalize_mcc(raw)


def _compact(s):
    return re.sub(r"[^A-Z]", "", (s or "").upper())


_STATE_COMPACT = sorted(((_compact(s), s) for s in STATES), key=lambda x: -len(x[0]))


def state_of_compact(full):
    """state detection that survives words broken by PDF line wraps ('Maharas htra')."""
    st = state_of(full)
    if st:
        return st
    c = _compact(full)
    best = max(((c.rfind(k), s) for k, s in _STATE_COMPACT if k in c), default=(-1, ""))
    return best[1]


def canonical_institutes(raw, al):
    """MCC prints a college's short name in the trail columns of the next round's file. Joining those to the
    full 'Name, address, State, PIN' strings of the earlier round teaches us the official short name for
    every full string; comparing on letters-only keys makes this immune to words broken by line wraps."""
    pairs = []
    for rnd, nxt, col in (("R1", "R2", "prev1_institute"), ("R2", "R3", "prev1_institute"),
                          ("R1", "R3", "prev2_institute")):
        a = raw[(raw["round"] == rnd) & (raw["institute"] != "-")][["year", "rank", "institute"]]
        b = raw[(raw["round"] == nxt) & (raw[col] != "-") & (raw[col] != "")][["year", "rank", col]]
        m = a.merge(b, on=["year", "rank"])
        pairs.append(pd.DataFrame({"full": m["institute"].map(_compact), "short": m[col]}))
    pairs = pd.concat(pairs)
    pairs["skey"] = pairs["short"].map(_compact)
    full2short = pairs.groupby("full")["skey"].agg(lambda s: s.value_counts().index[0]).to_dict()
    # readable text for each short key: the most common variant, lightly cleaned
    disp = (pairs.assign(short=pairs["short"].str.replace(r"\s*,\s*,", ",", regex=True).str.strip(" ,"))
            .groupby("skey")["short"].agg(lambda s: s.value_counts().index[0]).to_dict())
    shorts_by_len = sorted(disp, key=len, reverse=True)

    cache = {}

    def resolve(full):
        if full in cache:
            return cache[full]
        c = _compact(full)
        sk = full2short.get(c)
        if sk is None:  # never appeared in a trail: longest short name that the full string starts with
            sk = next((s for s in shorts_by_len if len(s) >= 12 and c.startswith(s)), None)
        cache[full] = (disp[sk] if sk else institute_name(full)), (sk or _compact(institute_name(full)))
        return cache[full]

    res = al["institute_full"].map(resolve)
    al["institute"] = res.str[0]
    al["inst_key"] = res.str[1]
    al["inst_state"] = al["institute_full"].map(state_of_compact)
    # fill a missing state from other rows of the same college
    mode = al[al["inst_state"] != ""].groupby("inst_key")["inst_state"].agg(lambda s: s.value_counts().index[0])
    miss = al["inst_state"] == ""
    al.loc[miss, "inst_state"] = al.loc[miss, "inst_key"].map(mode).fillna("")
    # one display name per (key, state): prefer the most frequent
    name = al.groupby(["inst_key", "inst_state"])["institute"].agg(lambda s: s.value_counts().index[0])
    al["institute"] = [name.get((k, s), n) for k, s, n in zip(al["inst_key"], al["inst_state"], al["institute"])]
    # name map reused by the app when a new PDF is uploaded
    fm = al.assign(key=al["institute_full"].map(_compact)).drop_duplicates("key")[["key", "institute", "inst_state"]]
    sm_ = al.drop_duplicates(["inst_key", "inst_state"])[["inst_key", "institute", "inst_state"]].rename(columns={"inst_key": "key"})
    pd.concat([fm.assign(kind="full"), sm_.assign(kind="short")]).to_parquet(
        os.path.join(OUT, "institute_map.parquet"), index=False)
    print(f"  canonical MCC institutes: {al['institute'].nunique()} names "
          f"({len(full2short)} learned from trails, {sum(1 for v in cache.values())} full strings)")
    return al


def build_journeys(raw, codes):
    """One row per (year, rank) with R1/R2/R3/stray seats, from the R3 file (+ stray files)."""
    r3 = raw[raw["round"] == "R3"].copy()

    def seat(q, inst, course):
        if not inst or inst == "-":
            return ""
        c = codes.get(course, course)
        return f"{quota_of(q)[0]} · {institute_name(inst) or inst} · {branch_of(c)[0]}"
    j = pd.DataFrame({
        "year": r3["year"], "rank": r3["rank"],
        "r1_seat": [seat(*x) for x in zip(r3.prev2_quota, r3.prev2_institute, r3.prev2_course)],
        "r1_status": r3["prev2_status"].replace({"-": ""}),
        "r2_seat": [seat(*x) for x in zip(r3.prev1_quota, r3.prev1_institute, r3.prev1_course)],
        "r2_status": r3["prev1_status"].replace({"-": ""}),
        "r3_seat": [seat(*x) for x in zip(r3.quota, r3.institute, r3.course)],
        "r3_remarks": r3["remarks"].map(clean_remark),
        "category": r3["candidate_cat"].replace({"-": ""}),
    })
    stray = raw[raw["round"].isin(["STRAY", "SPSTRAY"])]
    st = pd.DataFrame({"year": stray["year"], "rank": stray["rank"], "round": stray["round"],
                       "seat": [seat(*x) for x in zip(stray.quota, stray.institute, stray.course)]})
    for rnd, col in (("STRAY", "stray_seat"), ("SPSTRAY", "special_stray_seat")):
        j = j.merge(st[st["round"] == rnd][["year", "rank", "seat"]].rename(columns={"seat": col}),
                    on=["year", "rank"], how="outer")
    return j.fillna("").sort_values(["year", "rank"])


# ---------------------------------------------------------------------------------------------- States
BIHAR_PRIVATE = re.compile(r"SASARAM|KATIHAR|KISHANGANJ|MGMMC|MATA GUJRI|MADHUBANI|KOSHI|SAHARSA|NETAJI|RDJM|"
                           r"TURKI|SHRI NARAYAN|NARAYAN MEDICAL|BUDHA|BUDDHA")
BIHAR_NAMES = [(r"^P\.?M\.?C\.?\s*PATNA", "Patna Medical College, Patna"),
               (r"^N\.?M\.?C\.?\s*PATNA", "Nalanda Medical College, Patna"),
               (r"D\.?M\.?C\.?\s*(LAHERIASARAI|DARBHANGA)", "Darbhanga Medical College, Laheriasarai"),
               (r"S\.?K\.?M\.?C", "SKMCH, Muzaffarpur"), (r"A\.?N\.?M\.?M\.?C", "ANMMC, Gaya"),
               (r"J\.?L\.?N\.?M\.?C", "JLNMC, Bhagalpur"), (r"I\.?G\.?I\.?M\.?S", "IGIMS, Patna"),
               (r"BETTIAH", "Government Medical College, Bettiah"), (r"PAWAPURI", "BMIMS (VIMS), Pawapuri"),
               (r"PURNEA", "GMC Purnea"), (r"MADHEPURA", "JKTMC, Madhepura"),
               (r"N\.?M\.?C\s*&\.?\s*H.*SASARAM|NARAYAN MEDICAL COLLEGE", "Narayan Medical College, Sasaram"),
               (r"K\.?M\.?C\.?\s*KATIHAR", "Katihar Medical College, Katihar"),
               (r"MGMMC|MATA GUJRI", "Mata Gujri Memorial MC, Kishanganj"),
               (r"MADHUBANI", "Madhubani Medical College, Madhubani"),
               (r"KOSHI", "Lord Buddha Koshi MC, Saharsa"), (r"NETAJI", "Netaji Subhas MC, Bihta"),
               (r"RDJM|TURKI", "RDJM Medical College, Muzaffarpur"),
               (r"SHRI NARAYAN", "Shri Narayan Medical Institute, Saharsa")]
ODISHA_PRIVATE = re.compile(r"HI-?TECH|DRIEMS|KIMS|KALINGA|SUM |IMS AND SUM|JAGANNATH")
ODISHA_NAMES = [(r"^SCB", "SCB MCH, Cuttack"), (r"^MKCG", "MKCG MCH, Berhampur"), (r"VIMSAR", "VIMSAR, Burla"),
                (r"PGIMER|CAPITAL HOSPITAL", "PGIMER & Capital Hospital, Bhubaneswar"),
                (r"S ?J MCH|PURI", "SJ MCH, Puri"), (r"PRM", "PRM MCH, Baripada"),
                (r"B ?B MCH", "BB MCH, Balangir"), (r"F ?M MCH", "FM MCH, Balasore"), (r"SLN", "SLN MCH, Koraput"),
                (r"AHPGIC", "AHPGIC, Cuttack"),
                (r"HI-?TECH MCH BHUBANESWAR", "Hi-Tech MCH, Bhubaneswar"),
                (r"HI-?TECH MCH ROURKELA", "Hi-Tech MCH, Rourkela"), (r"DRIEMS", "DRIEMS, Tangi")]


def canon(name, table):
    u = name.upper()
    for rx, n in table:
        if re.search(rx, u):
            return n
    return re.sub(r"\s+", " ", name).strip().title()


def load_bihar(d=None):
    if d is None:
        d = pd.read_csv(os.path.join(INTERIM, "states", "bihar.csv"), dtype=str, keep_default_na=False)
    d = d.astype(str).replace({"nan": "", "None": ""})
    for c in ("candidate_cat", "allotted_cat", "remarks", "status", "institute", "course", "seat_type"):
        d[c] = d[c].map(undouble)   # bold text in some PDFs is extracted with every letter doubled
    d["status"] = d["status"].map(clean_status)
    d["seat_type"] = d["seat_type"].map(undouble)
    # some files put the seat remark in the status column and vice-versa
    swap = d["status"].str.match(r"(?i)against|jump|compensation") & ~d["remarks"].str.match(r"(?i)against|jump|compensation")
    d.loc[swap, ["remarks", "status"]] = d.loc[swap, ["status", "remarks"]].values
    seat_cat = d["remarks"].str.extract(r"(?i)(?:against|on)\s+(\w+)\s+(?:category\s+)?seat")[0].str.upper()
    comp = d["remarks"].str.extract(r"(?i)compensation seat \w+ against (\w+)")[0].str.upper()
    seat_cat = comp.fillna(seat_cat)
    d["quota_code"] = seat_cat.map(lambda c: {"NRI": "NRI", "MM": "MANAGEMENT", "SM": "MANAGEMENT"}.get(c, "STATE"))
    d["quota_name"] = d["quota_code"].map({"NRI": "NRI (private college)", "MANAGEMENT": "Management (private college)",
                                           "STATE": "State Quota"})
    d["allotted_cat"] = d["allotted_cat"].where(d["allotted_cat"] != "", seat_cat.fillna(""))
    d["institute_full"] = d["institute"]
    d["institute"] = d["institute"].map(lambda n: canon(n, BIHAR_NAMES))
    d["college_type"] = d["institute_full"].str.upper().map(
        lambda n: "Private" if BIHAR_PRIVATE.search(n) else ("DNB-Govt" if re.search(r"SADAR|LNJP|S\.H\.|BIMHAS", n) else "Govt"))
    d["course_raw"] = d["course"]
    d["degree"] = [("DNB Diploma" if "DIPL" in s.upper() else "DNB") if "DNB" in s.upper()
                   else ("Diploma" if "DIPLOMA" in s.upper() else "MD/MS") for s in d["seat_type"]]
    d["counselling"] = "Bihar State"
    d["remarks"] = d["remarks"].str.cat(d["status"], sep=" · ").str.strip(" ·")
    d["seat_status"] = d["status"]
    return d


def load_odisha():
    d = pd.read_csv(os.path.join(INTERIM, "states", "odisha.csv"), dtype=str, keep_default_na=False)
    d = d[d["rank"] != ""].copy()
    d["rank"] = d["rank"].astype(float).astype(int).astype(str)
    mgt = d["institute"].str.contains(r"\(MGT\)", case=False)
    d["quota_code"] = mgt.map({True: "MANAGEMENT", False: "STATE"})
    d["quota_name"] = mgt.map({True: "Management (private college)", False: "State Quota"})
    d["institute_full"] = d["institute"]
    d["institute"] = d["institute"].str.replace(r"\s*\(MGT\)", "", regex=True).map(lambda n: canon(n, ODISHA_NAMES))
    d["college_type"] = d["institute_full"].str.upper().map(
        lambda n: "Private" if ODISHA_PRIVATE.search(n) else ("DNB-Govt" if re.search(r"\bDHH\b|\bRGH\b", n) else "Govt"))
    d["course_raw"] = d["course"]
    d["degree"] = "MD/MS"
    d["counselling"] = "Odisha State"
    d["seat_status"] = d["status"]
    d["remarks"] = d["status"]
    return d


def finish_state(d, state):
    d = d.copy()
    d["year"] = d["year"].astype(int)
    d["rank"] = pd.to_numeric(d["rank"], errors="coerce")
    d = d[d["rank"].notna()].copy()
    d["rank"] = d["rank"].astype(int)
    b = d["course"].map(branch_of)
    d["branch"], d["clinical_type"] = b.str[0], b.str[1]
    ac = d["allotted_cat"].map(category_of)
    d["state_cat"] = d["allotted_cat"].str.upper()
    d["allotted_cat"], d["allotted_pwd"] = ac.str[0], ac.str[1]
    cc = d["candidate_cat"].map(category_of)
    d["candidate_cat"], d["candidate_pwd"] = cc.str[0].replace({"Open": "General"}), cc.str[1]
    d["inst_state"] = state
    d["course"] = d["course_raw"]
    for c in ("option_no", "prev_seat", "prev_status"):
        d[c] = ""
    return d


# ---------------------------------------------------------------------------------------------- NMC matrix
def load_seat_matrix():
    sm = pd.read_csv(os.path.join(INTERIM, "nmc_seat_matrix.csv"))
    b = sm["course"].map(branch_of)
    sm["branch"], sm["clinical_type"] = b.str[0], b.str[1]
    sm["degree"] = sm["course"].map(degree_of)
    sm["college_type"] = sm["category"].str.replace(".", "", regex=False).replace({"Pvt": "Private"})
    sm["state"] = sm["state"].map(lambda s: state_of(s) or s)
    sm["key"] = sm["college"].map(name_key)
    return sm


_GENERIC = {"MEDICAL", "MEDICA", "COLLEGE", "COLLEG", "COLLGE", "HOSPITAL", "INSTITUTE", "OF", "AND", "SCIENCES",
            "SCIENCE", "RESEARCH", "GOVERNMENT", "GOVT", "CENTRE", "CENTER", "THE", "UNIVERSITY", "POST", "GRADUATE",
            "POSTGRADUATE", "PG", "MED", "COL", "HOSP", "INST", "DEEMED", "TO", "BE", "NEW", "MC", "MCH", "IMS",
            "ACADEMY", "HIGHER", "EDUCATION", "AT", "IN", "FOR", "AMP", "STATE", "DR", "SHRI", "SRI", "SMT"}


def _distinct(name):
    toks = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper().replace("&", " ")).split()
    return [t for t in toks if t not in _GENERIC and len(t) > 1]


def link_to_matrix(inst, sm):
    """Map (institute, state) -> NMC college name. Compare only the distinctive words (city, founder name...)
    so that 'JSS Medical College' does not match 'Raja Rajeswari Medical College'."""
    out = {}
    by_state = {s: [(c, " ".join(sorted(set(_distinct(c))))) for c in g["college"].unique()]
                for s, g in sm.groupby("state")}
    everywhere = [(c, cd, s) for s, lst in by_state.items() for c, cd in lst]
    for name, st in inst:
        # unknown state -> search the whole country (the match also tells us the state)
        cands = [(c, cd, st) for c, cd in by_state.get(st, [])] if st else everywhere
        a = set(_distinct(name))
        if not cands or not a:
            continue
        best, best_score = None, 0
        for c, cd, cst in cands:
            b = set(cd.split())
            if not b:
                continue
            common = a & b
            score = fuzz.token_sort_ratio(" ".join(sorted(a)), cd)
            # all of our distinctive words appear in the NMC name (or vice-versa with >= 2 shared words)
            if common and (a <= b or (b <= a and len(common) >= 2)):
                score = max(score, 85 + 5 * min(len(common), 3))
            if score > best_score:
                best, best_score = (c, cst), score
        if best_score >= (88 if st else 93):
            out[(name, st)] = best
    return out


# ---------------------------------------------------------------------------------------------- main
COLS = ["counselling", "year", "round", "round_no", "round_label", "rank", "quota_code", "quota_name", "institute",
        "inst_state", "college_type", "branch", "clinical_type", "degree", "course", "allotted_cat", "allotted_pwd",
        "candidate_cat", "candidate_pwd", "option_no", "remarks", "seat_status", "prev_seat", "prev_status",
        "candidate_type", "state_rank", "nmc_college", "institute_full"]


def main():
    os.makedirs(OUT, exist_ok=True)
    print("loading MCC ...")
    raw, mcc = load_mcc()
    mcc = canonical_institutes(raw, mcc)
    codes = mcc_code_names()
    print(f"  {len(mcc)} MCC allotments, {len(codes)} course codes")
    journeys = build_journeys(raw, codes)
    journeys.to_parquet(os.path.join(OUT, "journeys.parquet"), index=False)
    print(f"  {len(journeys)} journeys")

    print("loading states ...")
    bihar = finish_state(load_bihar(), "Bihar")
    odisha = finish_state(load_odisha(), "Odisha")
    print(f"  bihar {len(bihar)}, odisha {len(odisha)}")

    al = pd.concat([mcc, bihar, odisha], ignore_index=True)
    al["round_no"] = al["round"].map(ROUND_NO)
    al["round_label"] = al["round"].map(ROUND_LABEL)

    sm = load_seat_matrix()
    sm.to_parquet(os.path.join(OUT, "seat_matrix_2026.parquet"), index=False)
    pairs = al.loc[~al["college_type"].str.startswith("DNB"), ["institute", "inst_state"]].drop_duplicates()
    link = link_to_matrix(pairs.itertuples(index=False, name=None), sm)
    hit = [link.get((i, s)) for i, s in zip(al["institute"], al["inst_state"])]
    al["nmc_college"] = [h[0] if h else "" for h in hit]
    al["inst_state"] = [s or (h[1] if h else "") for s, h in zip(al["inst_state"], hit)]
    print(f"  linked {len(link)} of {len(pairs)} institutes to the NMC 2026 seat matrix")

    for c in COLS:
        if c not in al:
            al[c] = ""
    al = al[COLS]
    for c in ("allotted_pwd", "candidate_pwd"):
        al[c] = al[c].fillna(False).astype(bool)
    for c in al.columns:
        if al[c].dtype == object:
            al[c] = al[c].fillna("").astype(str)
    al.to_parquet(os.path.join(OUT, "allotments.parquet"), index=False)

    closing = closing_ranks(al)
    closing.to_parquet(os.path.join(OUT, "closing.parquet"), index=False)
    print(f"wrote {len(al)} allotments, {len(closing)} closing-rank groups")
    print(al.groupby(["counselling", "year", "round"]).size().to_string())


if __name__ == "__main__":
    main()
