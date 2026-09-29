import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import data  # noqa: E402
from core.predict import CENTRAL_QUOTAS, Profile, choice_order, eligibility, predict  # noqa: E402
from core.ui import not_ready, setup, style_chance  # noqa: E402

setup("Predictor", "🎯")
if not data.data_ready():
    not_ready()

closing = data.closing()
st.title("🎯 NEET PG Counselling Predictor")
st.caption("Predictions use closing ranks of MCC (All India) 2023-2025 and Bihar / Odisha state counselling. "
           "They are estimates from past trends, not guarantees. Always verify with the official MCC / state notices.")

branches = closing.groupby("branch")["allotted"].sum().sort_values(ascending=False).index.tolist()
prev = st.session_state.get("profile", {})

with st.expander("👤 Your details", expanded="profile" not in st.session_state):
    with st.form("profile_form"):
        c1, c2, c3, c4 = st.columns(4)
        rank = c1.number_input("NEET PG All India Rank", 1, 300000, int(prev.get("rank", 71385)), step=1)
        category = c2.selectbox("NEET category", ["General", "EWS", "OBC", "SC", "ST"],
                                index=["General", "EWS", "OBC", "SC", "ST"].index(prev.get("category", "General")))
        pwd = c3.checkbox("Person with Disability (PwD)", prev.get("pwd", False))
        in_service = c4.checkbox("In-service candidate", prev.get("in_service", False))

        c1, c2, c3, c4 = st.columns(4)
        domicile = c1.selectbox("Domicile state", data.INDIAN_STATES,
                                index=data.INDIAN_STATES.index(prev.get("domicile", "Bihar")))
        mbbs_state = c2.selectbox("State where you did MBBS", data.INDIAN_STATES,
                                  index=data.INDIAN_STATES.index(prev.get("mbbs_state", "Odisha")))
        seats = ["Govt college (AIQ seat)", "Govt college (state quota seat)", "Private college"]
        mbbs_seat = c3.selectbox("Your MBBS seat was", seats, index=seats.index(prev.get("mbbs_seat", seats[2])))
        unis = ["None of these"] + list(CENTRAL_QUOTAS.values())
        mbbs_university = c4.selectbox("MBBS from a central university?", unis,
                                       index=unis.index(prev.get("mbbs_university") or "None of these"))
        state_cats = ["(same as NEET category)", "BC", "EBC", "SEBC", "EWS", "SC", "ST"]
        state_category = c1.selectbox("State category (domicile state list)", state_cats,
                                      index=state_cats.index(prev.get("state_category") or "(same as NEET category)"),
                                      help="Bihar splits OBC into BC and EBC; Odisha uses SEBC.")

        preferred = st.multiselect("Preferred branches (in order of preference)", branches,
                                   default=[b for b in prev.get("preferred_branches", []) if b in branches])
        c1, c2, c3 = st.columns(3)
        degrees = c1.multiselect("Course types", ["MD", "MS", "MD/MS", "DNB", "6-yr Direct", "Diploma", "DNB Diploma"],
                                 default=prev.get("degrees", ["MD", "MS", "MD/MS", "DNB", "6-yr Direct"]))
        ctypes = c2.multiselect("College types", ["Govt", "DNB-Govt", "Deemed", "Private", "DNB-Private"],
                                default=prev.get("college_types", ["Govt", "DNB-Govt", "Deemed", "Private", "DNB-Private"]))
        clin = c3.multiselect("Branch types", ["Clinical", "Para-clinical", "Non-clinical", "Unknown"],
                              default=prev.get("clinical_types", ["Clinical", "Para-clinical", "Non-clinical", "Unknown"]))
        c1, c2, c3 = st.columns(3)
        nri = c1.checkbox("NRI sponsored", prev.get("nri", False))
        uncertain = c2.checkbox("Show seats where eligibility is uncertain", prev.get("include_uncertain", True))
        show_all = c3.checkbox("Also show seats with no realistic chance", False)
        submitted = st.form_submit_button("🔍 Predict", type="primary", width="stretch")

    if submitted:
        st.session_state["profile"] = dict(
            rank=int(rank), category=category, pwd=pwd, in_service=in_service, domicile=domicile,
            mbbs_state=mbbs_state, mbbs_seat=mbbs_seat,
            mbbs_university="" if mbbs_university == "None of these" else mbbs_university,
            state_category="" if state_category.startswith("(") else state_category,
            preferred_branches=preferred, degrees=degrees, college_types=ctypes, clinical_types=clin,
            nri=nri, include_uncertain=uncertain)
        st.session_state["show_all"] = show_all
        st.rerun()

if "profile" not in st.session_state:
    st.info("Fill in your details above and press **Predict**.")
    st.stop()

p = Profile(**st.session_state["profile"])

# ------------------------------------------------------------------ eligibility summary
with st.expander("✅ Which counsellings / quotas you can take part in", expanded=False):
    el = pd.DataFrame(eligibility(p), columns=["Counselling", "Quota", "Eligible", "Rule"])
    el["Eligible"] = el["Eligible"].map({True: "✅ Yes", False: "❌ No", None: "⚠️ Uncertain"}).fillna("⚠️ Uncertain")
    st.dataframe(el, hide_index=True, width="stretch")
    st.caption("State quotas covered so far: Bihar and Odisha. Other states can be added to the pipeline.")

pred = predict(p, closing, data.seat_matrix(), data.policy(), data.deemed_fees(),
               show_all=st.session_state.get("show_all", False))
if pred.empty:
    st.warning("No matching seats found with these filters.")
    st.stop()

# ------------------------------------------------------------------ headline
m = st.columns(5)
for col, lab in zip(m, ["High", "Good", "Borderline", "Low (reach)", "Stray only"]):
    col.metric(lab, int((pred["chance"] == lab).sum()))

top = pred[pred["chance"].isin(["High", "Good"])].sort_values(["section", "tier", "est_closing"])


def headline(label, rows):
    if len(rows):
        b = rows.iloc[0]
        st.success(f"**{label}:** {b.branch} ({b.degree}) at **{b.institute}**, {b.inst_state} — {b.counselling} / "
                   f"{b.quota_name}, {b.college_type}. Est. closing ≈ {int(b.est_closing):,} (your rank {p.rank:,}), "
                   f"likely from **{b.best_round or 'later rounds'}**.")


headline("Best Govt option", top[top["college_type"].isin(["Govt", "DNB-Govt"])])
if p.preferred_branches:
    headline("Best option in your preferred branches",
             top[top["preferred"]].sort_values(["pref_rank", "tier", "section", "est_closing"]))

year_cols = sorted([c for c in pred.columns if c[:4].isdigit()], reverse=True)
BASE = {"counselling": "Counselling", "quota_name": "Quota", "institute": "College", "inst_state": "State",
        "college_type": "Type", "branch": "Branch", "degree": "Degree", "clinical_type": "Clinical?",
        "allotted_cat": "Seat category", "est_closing": "Est. 2026 closing", "chance": "Chance",
        "best_round": "Likely from", "years_got": "Years you'd have got it", "seats_2026": "Seats 2026 (NMC)",
        "surrender_pct": "Surrender %", "cost_info": "Fee / Bond / Stipend (indicative)", "elig_note": "Eligibility note"}


def show(df, key):
    if df.empty:
        st.caption("Nothing here.")
        return
    t = df.rename(columns=BASE)
    cols = [c for c in BASE.values() if c in t.columns][:13] + year_cols + ["Fee / Bond / Stipend (indicative)"]
    t = t[list(dict.fromkeys(cols))]
    if "uncertain" in df and df["uncertain"].any():
        t.insert(0, "⚠️", df["uncertain"].map({True: "verify eligibility", False: ""}).values)
    st.dataframe(style_chance(t), hide_index=True, width="stretch", height=min(600, 38 + 35 * len(t)),
                 column_config={c: st.column_config.NumberColumn(format="%d") for c in year_cols + ["Est. 2026 closing"]})
    st.download_button("⬇️ Download CSV", t.to_csv(index=False).encode(), f"{key}.csv", "text/csv", key=f"dl_{key}")


def sections(df, key):
    for sec, name in ((0, "🇮🇳 All India (MCC) — AIQ / Deemed / DNB"), (1, "🏛️ State quota")):
        part = df[df["section"] == sec]
        st.subheader(f"{name}  ·  {len(part)} options")
        show(part, f"{key}_{sec}")


def all_options(key):
    f1, f2, f3 = st.columns(3)
    fb = f1.multiselect("Branch", sorted(pred["branch"].unique()), key=f"fb_{key}")
    fs = f2.multiselect("State", sorted(pred["inst_state"].unique()), key=f"fs_{key}")
    fc = f3.multiselect("Chance", ["High", "Good", "Borderline", "Low (reach)", "Stray only"], key=f"fc_{key}")
    d = pred
    if fb:
        d = d[d["branch"].isin(fb)]
    if fs:
        d = d[d["inst_state"].isin(fs)]
    if fc:
        d = d[d["chance"].isin(fc)]
    sections(d, key)


if p.preferred_branches:
    tabs = st.tabs(["⭐ Preferred branches", "📋 All options", "🧾 Suggested choice-filling order", "📈 Round-wise view"])
    with tabs[0]:
        sections(pred[pred["preferred"]], "preferred")
    with tabs[1]:
        all_options("all")
else:
    # no branch preference: all options first (Govt before private, best chance first)
    tabs = st.tabs(["📋 All options", "🧾 Suggested choice-filling order", "📈 Round-wise view"])
    tabs = [None] + list(tabs)
    with tabs[1]:
        st.caption("No preferred branches selected - showing every option you have a chance at. "
                   "Use the Branch filter below, or pick preferred branches in **Your details**.")
        all_options("all")
with tabs[2]:
    st.caption("Order: All India before State → your preferred branches in order → Govt before DNB-Govt before "
               "Deemed/Private → most competitive (lowest closing rank) first, so dream options sit above safe ones. "
               "Fill ALL of these (and more) — in MCC you are never forced to take a lower choice than one you get.")
    co = choice_order(pred)
    show(co.rename(columns={"choice_no": "Choice #"}).assign(**{"Choice #": co["choice_no"]}), "choice_order")
with tabs[3]:
    st.caption("Closing rank in each round for your eligible seats. Blank = no allotment of that seat group in that "
               "round (seat not offered, or filled in an earlier round).")
    r = pred[["institute", "branch", "degree", "quota_name", "allotted_cat", "chance"] + year_cols].rename(columns=BASE)
    st.dataframe(style_chance(r), hide_index=True, width="stretch", height=600,
                 column_config={c: st.column_config.NumberColumn(format="%d") for c in year_cols})

with st.expander("How is this predicted?"):
    st.markdown("""
* For every **seat group** (college × branch × course type × quota × seat category) we take the **closing rank**
  (last rank allotted) in each round of 2023, 2024 and 2025.
* The **estimated 2026 closing** is the deepest closing rank up to Round 3, averaged across years with weights
  2025 = 3, 2024 = 2, 2023 = 1.
* **Chance** = your rank ÷ estimated closing: ≤ 0.85 High · ≤ 1.00 Good · ≤ 1.15 Borderline · ≤ 1.35 Low (reach).
  *Stray only* = reachable only in stray-vacancy rounds historically.
* **Likely from** = the earliest round whose historical closing rank already covered your rank.
* **Surrender %** = share of past allottees who surrendered / didn't join, i.e. how often this seat comes back later.
* Caveats: seat numbers change every year (see *Seats 2026*), the number of NEET PG candidates changes, and cutoffs
  can shift a lot when new seats are added. Treat Borderline / Reach as options to **fill**, not to count on.
""")
