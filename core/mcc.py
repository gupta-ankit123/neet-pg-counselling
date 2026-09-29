"""Normalise raw MCC result rows (as produced by pipeline/parse_mcc.parse_row) into the allotments schema."""
import re

import pandas as pd

from core.normalize import (branch_of, category_of, clean_remark, clean_status, degree_of, dnb_hospital_type, institute_name,
                            quota_of, state_of)

ROUND_NO = {"R1": 1, "R1_UPGRADE": 1.5, "R2": 2, "R3": 3, "R4": 3.5, "STRAY": 4, "SPSTRAY": 5, "FINAL_ADMITTED": 6}
ROUND_LABEL = {"R1": "Round 1", "R1_UPGRADE": "Round 1 (upgrade)", "R2": "Round 2", "R3": "Round 3",
               "R4": "Round 4", "STRAY": "Stray", "SPSTRAY": "Special Stray", "FINAL_ADMITTED": "Final admitted"}
NEXT_ROUND = {"R1": "R2", "R2": "R3", "R3": "R4"}


def seat_status_from_next(raw: pd.DataFrame) -> pd.DataFrame:
    """Status (Reported / Not Reported / Seat Surrendered) of each round-N seat, read from the round-(N+1) trail."""
    st = raw[raw["round"].isin(NEXT_ROUND.values())][["year", "round", "rank", "prev1_status"]].copy()
    st["round"] = st["round"].map({v: k for k, v in NEXT_ROUND.items()})
    return st.rename(columns={"prev1_status": "seat_status"}).replace({"seat_status": {"-": ""}})


def normalize_mcc(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw["year"] = raw["year"].astype(int)
    raw["rank"] = raw["rank"].astype(int)
    al = raw[raw["institute"] != "-"].merge(seat_status_from_next(raw), on=["year", "round", "rank"], how="left")
    al["seat_status"] = al["seat_status"].fillna("").map(clean_status)
    q = al["quota"].map(quota_of)
    al["quota_code"], al["quota_name"] = q.str[0], q.str[1]
    al["institute_full"] = al["institute"]
    al["institute"] = al["institute_full"].map(institute_name)
    al["inst_state"] = al["institute_full"].map(state_of)
    b = al["course"].map(branch_of)
    al["branch"], al["clinical_type"] = b.str[0], b.str[1]
    al["degree"] = al["course"].map(degree_of)
    ac = al["allotted_cat"].map(category_of)
    al["allotted_cat"], al["allotted_pwd"] = ac.str[0], ac.str[1]
    cc = al["candidate_cat"].map(category_of)
    al["candidate_cat"], al["candidate_pwd"] = cc.str[0].replace({"Open": "General"}), cc.str[1]

    def ctype(r):
        if r.quota_code == "DNB":
            return "DNB-" + dnb_hospital_type(r.institute_full)
        if r.quota_code in ("DEEMED", "NRI", "MINORITY"):
            return "Deemed"
        return "Govt"
    al["college_type"] = al.apply(ctype, axis=1) if len(al) else ""
    al["counselling"] = "MCC (All India)"
    al["remarks"] = al["remarks"].map(clean_remark)
    for c in ("prev1_quota", "prev1_institute", "prev1_course", "prev1_status"):
        if c not in al:
            al[c] = ""
    al["prev_seat"] = [" | ".join(x for x in t if x and x != "-")
                       for t in zip(al["prev1_quota"], al["prev1_institute"], al["prev1_course"])]
    al["prev_status"] = al["prev1_status"].replace({"-": ""}).map(clean_status)
    al["candidate_type"] = ""
    al["state_rank"] = ""
    al["round_no"] = al["round"].map(ROUND_NO)
    al["round_label"] = al["round"].map(ROUND_LABEL)
    return al


CLOSING_KEYS = ["counselling", "year", "round", "round_no", "round_label", "quota_code", "quota_name", "institute",
                "inst_state", "college_type", "branch", "clinical_type", "degree", "allotted_cat", "allotted_pwd",
                "candidate_type"]


def closing_ranks(al: pd.DataFrame) -> pd.DataFrame:
    al = al.assign(_surr=al["seat_status"].str.contains("Surrender", case=False),
                   _notrep=al["seat_status"].str.contains("Not Reported", case=False))
    g = al.groupby(CLOSING_KEYS, dropna=False)
    out = g.agg(opening=("rank", "min"), closing=("rank", "max"), allotted=("rank", "size"),
                surrendered=("_surr", "sum"), not_reported=("_notrep", "sum"),
                nmc_college=("nmc_college", "first") if "nmc_college" in al else ("institute", lambda s: "")).reset_index()
    return out


def apply_institute_map(al: pd.DataFrame, imap: pd.DataFrame) -> pd.DataFrame:
    """Give uploaded rows the same canonical college names as the historical data."""
    if imap is None or imap.empty or al.empty:
        return al
    comp = lambda x: re.sub(r"[^A-Z]", "", (x or "").upper())  # noqa: E731
    full = imap[imap["kind"] == "full"].set_index("key")
    shorts = imap[imap["kind"] == "short"].copy()
    shorts = shorts[shorts["key"].str.len() >= 12].sort_values("key", key=lambda s: s.str.len(), ascending=False)
    short_list = list(zip(shorts["key"], shorts["institute"], shorts["inst_state"]))
    cache = {}

    def resolve(f, st):
        k = comp(f)
        if k in cache:
            return cache[k]
        if k in full.index:
            r = full.loc[k]
            cache[k] = (r["institute"], r["inst_state"] or st)
        else:
            hit = next(((n, s) for sk, n, s in short_list if k.startswith(sk) and (not st or not s or s == st)), None)
            cache[k] = hit or (None, st)
        return cache[k]

    res = [resolve(f, s) for f, s in zip(al["institute_full"], al["inst_state"])]
    al = al.copy()
    al["institute"] = [n or old for (n, _), old in zip(res, al["institute"])]
    al["inst_state"] = [s for _, s in res]
    return al
