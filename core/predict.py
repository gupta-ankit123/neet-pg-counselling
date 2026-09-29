"""Rank-based seat prediction from previous years' closing ranks."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

YEAR_WEIGHTS = {2025: 3.0, 2024: 2.0, 2023: 1.0}
MAIN_ROUNDS = [1, 2, 3]            # R1, R2, R3 (state R1 upgrade = 1.5 is folded into R1)
TYPE_TIER = {"Govt": 0, "DNB-Govt": 1, "Private": 2, "Deemed": 2, "DNB-Private": 3}
CHANCE_ORDER = ["High", "Good", "Borderline", "Low (reach)", "Stray only"]
CENTRAL_QUOTAS = {"DU": "Delhi University", "IPU": "IP University", "AMU": "Aligarh Muslim University",
                  "BHU": "Banaras Hindu University"}


@dataclass
class Profile:
    rank: int
    category: str = "General"            # General / EWS / OBC / SC / ST (NEET category)
    state_category: str = ""             # state list category, e.g. Bihar BC / EBC, Odisha SEBC
    pwd: bool = False
    domicile: str = ""
    mbbs_state: str = ""
    mbbs_seat: str = "Private college"   # 'Govt college (AIQ seat)' / 'Govt college (state quota seat)' / 'Private college'
    mbbs_university: str = ""            # for MCC central-university internal quotas
    in_service: bool = False
    preferred_branches: list = field(default_factory=list)
    degrees: list = field(default_factory=lambda: ["MD", "MS", "MD/MS", "DNB", "6-yr Direct"])
    college_types: list = field(default_factory=lambda: ["Govt", "DNB-Govt", "Deemed", "Private", "DNB-Private"])
    clinical_types: list = field(default_factory=lambda: ["Clinical", "Para-clinical", "Non-clinical", "Unknown"])
    nri: bool = False
    include_uncertain: bool = True


def eligibility(p: Profile):
    """-> list of (counselling, quota_code, allowed, note)"""
    rules = [("MCC (All India)", "AIQ", True, ""), ("MCC (All India)", "DNB", True, ""),
             ("MCC (All India)", "DEEMED", True, "Deemed university paid seat - high fees"),
             ("MCC (All India)", "NRI", p.nri, "Only NRI-sponsored candidates"),
             ("MCC (All India)", "AFMS", False, "Armed forces candidates only"),
             ("MCC (All India)", "MINORITY", False, "Minority community candidates only"),
             ("MCC (All India)", "ESI", False, "ESI insured persons' wards only")]
    for code, uni in CENTRAL_QUOTAS.items():
        rules.append(("MCC (All India)", code, p.mbbs_university == uni, f"Only for MBBS graduates of {uni}"))

    bihar_ok = p.mbbs_state == "Bihar"
    rules += [("Bihar State", "STATE", bihar_ok,
               "Needs MBBS from a Bihar medical college (PGMAC prospectus 6.1)"),
              ("Bihar State", "MANAGEMENT", bihar_ok or (p.include_uncertain and None),
               "Private-college management seats: eligibility for non-Bihar MBBS is unclear - verify with BCECEB"),
              ("Bihar State", "NRI", p.nri, "NRI candidates only")]
    odisha_ok = p.domicile == "Odisha" or (p.mbbs_state == "Odisha" and p.mbbs_seat.startswith("Govt college (AIQ"))
    rules += [("Odisha State", "STATE", odisha_ok,
               "Needs Odisha domicile, or MBBS from an Odisha Govt college under 15% AIQ (DMET guidelines F.1)"),
              ("Odisha State", "MANAGEMENT", odisha_ok,
               "Hi-Tech / DRIEMS management seats - same eligibility as state quota, UR only")]
    return rules


def allowed_categories(p: Profile, counselling: str):
    """Seat categories this candidate can occupy, per counselling."""
    if counselling == "MCC (All India)":
        cats = {"Open"} | ({p.category} if p.category != "General" else set())
    else:
        sc = (p.state_category or p.category).upper()
        m = {"BC": "OBC", "SEBC": "OBC", "OBC": "OBC", "EBC": "EBC", "EWS": "EWS", "SC": "SC", "ST": "ST"}
        cats = {"Open"}
        home = counselling.startswith(p.domicile) if p.domicile else False
        if sc in m and home:   # reservation benefits only for the state's own domiciles
            cats.add(m[sc])
        if counselling == "Odisha State" and "OBC" in cats:
            cats.discard("OBC")    # Odisha: OBC candidates are merged into UR
    return cats


def _weighted(vals):
    """vals: {year: closing} -> weighted estimate"""
    if not vals:
        return np.nan
    w = np.array([YEAR_WEIGHTS.get(y, 0.5) for y in vals])
    return float(np.dot(w, np.array(list(vals.values()), dtype=float)) / w.sum())


def chance_label(rank, est_main, est_stray):
    if not np.isnan(est_main):
        x = rank / est_main
        if x <= 0.85:
            return "High"
        if x <= 1.0:
            return "Good"
        if x <= 1.15:
            return "Borderline"
        if x <= 1.35:
            return "Low (reach)"
    if not np.isnan(est_stray) and rank <= est_stray:
        return "Stray only"
    return ""


def predict(p: Profile, closing: pd.DataFrame, seat_matrix: pd.DataFrame = None, policy: pd.DataFrame = None,
            deemed_fees: pd.DataFrame = None, show_all=False):
    rules = eligibility(p)
    allow = {(c, q): (ok, note) for c, q, ok, note in rules}
    df = closing.copy()
    df["rule"] = [allow.get((c, q), (False, "")) for c, q in zip(df["counselling"], df["quota_code"])]
    df["uncertain"] = [ok is None for ok, _ in df["rule"]]
    df["elig_note"] = df["rule"].str[1]
    df = df[[ok is True or (ok is None and p.include_uncertain) for ok, _ in df["rule"]]].copy()
    # category / PwD / candidate type
    keep = []
    for c, g in df.groupby("counselling"):
        cats = allowed_categories(p, c)
        m = g["allotted_cat"].isin(cats) & (p.pwd | ~g["allotted_pwd"].astype(bool))
        if c == "Odisha State":
            m &= g["candidate_type"].eq("In-service" if p.in_service else "Direct") | g["candidate_type"].eq("")
        keep.append(g[m])
    df = pd.concat(keep) if keep else df.iloc[0:0]
    df = df[df["degree"].isin(p.degrees) & df["college_type"].isin(p.college_types)
            & df["clinical_type"].isin(p.clinical_types)]
    if df.empty:
        return df

    df["rnd"] = df["round_no"].replace({1.5: 1})
    opt_keys = ["counselling", "quota_code", "quota_name", "institute", "inst_state", "college_type", "branch",
                "clinical_type", "degree", "allotted_cat", "allotted_pwd"]
    for k in opt_keys:
        if df[k].dtype == object:
            df[k] = df[k].fillna("")
    years = sorted(df["year"].unique())
    w = np.array([YEAR_WEIGHTS.get(int(y), 0.5) for y in years])

    def reach(rounds):
        """option x year matrix: deepest closing rank over the given rounds"""
        s = df[df["rnd"].isin(rounds)].groupby(opt_keys + ["year"])["closing"].max().unstack("year")
        return s.reindex(columns=years)

    def est(m):
        v = m.to_numpy(dtype=float)
        mask = ~np.isnan(v)
        den = (mask * w).sum(1)
        return pd.Series(np.where(den > 0, np.nansum(np.nan_to_num(v) * w, 1) / np.where(den > 0, den, 1), np.nan),
                         index=m.index)

    main = reach(MAIN_ROUNDS + [6])          # 6 = Odisha final-admitted list
    idx = main.index.union(reach([4, 5]).index)
    main = main.reindex(idx)
    out = pd.DataFrame(index=idx)
    out["est_closing"] = est(main)
    out["est_stray"] = est(reach([4, 5]).reindex(idx))
    hit = (main >= p.rank).sum(1)
    n = main.notna().sum(1)
    out["years_got"] = [f"{h}/{k}" if k else "" for h, k in zip(hit, n)]
    out["best_round"] = ""
    for r, lab in ((3, "Round 3"), (2, "Round 2"), (1, "Round 1")):   # overwrite downwards -> earliest round wins
        e = est(reach(list(range(1, r + 1)) + ([6] if r == 3 else [])).reindex(idx))
        out.loc[e >= p.rank, "best_round"] = lab
    out.loc[(out["best_round"] == "") & (out["est_stray"] >= p.rank), "best_round"] = "Stray"
    lab = [chance_label(p.rank, a, b) for a, b in zip(out["est_closing"], out["est_stray"])]
    # consistency cap: a seat you would have got in fewer than half of the years is at best Borderline
    order = {c: i for i, c in enumerate(CHANCE_ORDER)}
    for i, (h, k) in enumerate(zip(hit, n)):
        if k >= 2 and lab[i] in ("High", "Good") and h / k < 0.5:
            lab[i] = "Borderline"
    out["chance"] = lab
    hist = df.assign(col=df["year"].astype(str) + " " + df["rnd"].map(
        {1: "R1", 2: "R2", 3: "R3", 4: "Stray", 5: "Sp.Stray", 6: "Final"}).fillna("R?"))
    hist = hist.groupby(opt_keys + ["col"])["closing"].max().unstack("col").reindex(idx)
    agg = df.groupby(opt_keys).agg(surr=("surrendered", "sum"), allot=("allotted", "sum"),
                                   uncertain=("uncertain", "any"), elig_note=("elig_note", "first"),
                                   nmc_college=("nmc_college", "first")).reindex(idx)
    out["surrender_pct"] = (100 * agg["surr"] / agg["allot"].clip(lower=1)).round()
    out = out.join(agg[["uncertain", "elig_note", "nmc_college"]]).join(hist).reset_index()
    out["est_closing"] = out["est_closing"].round()
    out["est_stray"] = out["est_stray"].round()
    # best category row per seat (a reserved candidate may appear under Open and own category)
    out["_score"] = out["est_closing"].fillna(out["est_stray"]).fillna(0)
    out = out.sort_values("_score", ascending=False).drop_duplicates(
        ["counselling", "quota_code", "institute", "branch", "degree"])
    if not show_all:
        out = out[out["chance"] != ""]
    out = _decorate(out, p, seat_matrix, policy, deemed_fees)
    return out


def _decorate(out, p, seat_matrix, policy, deemed_fees):
    pref = {b: i for i, b in enumerate(p.preferred_branches)}
    out["pref_rank"] = out["branch"].map(pref).fillna(len(pref)).astype(int)
    out["preferred"] = out["branch"].isin(pref)
    out["section"] = np.where(out["counselling"].str.startswith("MCC"), 0, 1)
    out["tier"] = out["college_type"].map(TYPE_TIER).fillna(4)
    out["chance_ord"] = out["chance"].map({c: i for i, c in enumerate(CHANCE_ORDER)}).fillna(9)
    if seat_matrix is not None and len(out):
        sm = seat_matrix.groupby(["college", "branch"])["seats"].sum()
        out["seats_2026"] = [sm.get((c, b)) if c else None for c, b in zip(out["nmc_college"], out["branch"])]
    out["cost_info"] = [cost_info(r, policy, deemed_fees) for r in out.itertuples()]
    # "prediction" view: what you are most likely to get -> section, preferred first, govt first, best chance
    out = out.sort_values(["section", "pref_rank", "tier", "chance_ord", "est_closing"]).reset_index(drop=True)
    return out


def choice_order(pred: pd.DataFrame):
    """Suggested choice-filling order: AIQ before state; within each, preferred branches in order, govt before
    private, and most sought-after (lowest closing rank) first so that reach options sit above safe ones."""
    d = pred[pred["chance"].isin(["High", "Good", "Borderline", "Low (reach)"])].copy()
    d = d.sort_values(["section", "pref_rank", "tier", "est_closing"])
    d.insert(0, "choice_no", range(1, len(d) + 1))
    return d


_fee_cache = {}


def cost_info(r, policy, deemed_fees):
    parts = []
    if r.college_type == "Deemed" and deemed_fees is not None and len(deemed_fees):
        key = (r.institute, r.inst_state)
        if key not in _fee_cache:
            sub = deemed_fees[deemed_fees["state"] == r.inst_state]
            m = process.extractOne(r.institute, sub["college"].tolist(), scorer=fuzz.token_set_ratio) if len(sub) else None
            _fee_cache[key] = sub[sub["college"] == m[0]].iloc[0] if m and m[1] >= 85 else None
        f = _fee_cache[key]
        parts.append(f"Fee ₹{f.annual_fee_min/1e5:.1f}–{f.annual_fee_max/1e5:.1f} L/yr (range, all branches)"
                     if f is not None else "Deemed: fees typically ₹10–50 L/yr - check college")
    elif r.college_type.startswith("DNB"):
        parts.append("DNB: NBEMS fee ~₹1.25 L/yr; stipend per hospital (private DNB hospitals may charge more)")
    elif r.college_type == "Private":
        parts.append("Private (state): fee per state fee committee - see prospectus")
    if r.college_type in ("Govt", "DNB-Govt") and policy is not None:
        pol = policy[policy["state"] == r.inst_state]
        if len(pol):
            x = pol.iloc[0]
            s = f"Bond: {x.bond_years or '?'} yr, {x.bond_penalty or '?'}"
            if pd.notna(x.stipend_y1):
                s += f" · Stipend ~₹{int(x.stipend_y1):,}/mo (Y1)"
            if pd.notna(x.govt_tuition_per_year) and x.govt_tuition_per_year:
                s += f" · Fee {x.govt_tuition_per_year}"
            parts.append(s)
    return " | ".join(parts)
