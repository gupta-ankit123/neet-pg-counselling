import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import data  # noqa: E402
from core.ui import not_ready, setup  # noqa: E402

setup("Explore data", "📊")
if not data.data_ready():
    not_ready()

al = data.allotments()
st.title("📊 Explore previous years' allotments")

view = st.radio("View", ["Closing ranks (per college × branch × quota × category × round)", "Every allotment (row per candidate)"],
                horizontal=True)

with st.sidebar:
    st.header("Filters")
    prof = st.session_state.get("profile", {})
    rng = st.slider("Rank range", 1, int(al["rank"].max()), (1, int(al["rank"].max())), step=100)
    if prof and st.checkbox(f"Only ranks near mine ({prof['rank']:,} ± 25%)"):
        rng = (int(prof["rank"] * 0.75), int(prof["rank"] * 1.25))

    def ms(label, col, default=None):
        opts = sorted(x for x in al[col].dropna().unique() if x != "")
        return st.multiselect(label, opts, default=default or [])

    f = dict(
        counselling=ms("Counselling", "counselling"),
        year=st.multiselect("Year", sorted(al["year"].unique(), reverse=True)),
        round_label=ms("Round", "round_label"),
        quota_name=ms("Quota", "quota_name"),
        allotted_cat=ms("Seat category", "allotted_cat"),
        candidate_cat=ms("Candidate category", "candidate_cat"),
        inst_state=ms("College state", "inst_state"),
        college_type=ms("College type", "college_type"),
        clinical_type=ms("Clinical / non-clinical", "clinical_type"),
        branch=ms("Branch", "branch", prof.get("preferred_branches")),
        degree=ms("Course type", "degree"),
    )
    college_q = st.text_input("College name contains")
    remark_q = st.text_input("Remarks / status contains", placeholder="e.g. Surrendered, Upgraded, Not Reported")
    pwd = st.selectbox("PwD seats", ["All", "Exclude PwD seats", "Only PwD seats"])

d = al[(al["rank"] >= rng[0]) & (al["rank"] <= rng[1])]
for col, vals in f.items():
    if vals:
        d = d[d[col].isin(vals)]
if college_q:
    d = d[d["institute"].str.contains(college_q, case=False, na=False) |
          d["institute_full"].str.contains(college_q, case=False, na=False)]
if remark_q:
    d = d[d["remarks"].str.contains(remark_q, case=False, na=False) |
          d["seat_status"].str.contains(remark_q, case=False, na=False)]
if pwd != "All":
    d = d[d["allotted_pwd"] == (pwd == "Only PwD seats")]

c = st.columns(4)
c[0].metric("Allotments", f"{len(d):,}")
c[1].metric("Colleges", f"{d['institute'].nunique():,}")
c[2].metric("Surrendered (next round)", f"{d['seat_status'].eq('Seat Surrendered').sum():,}")
c[3].metric("Not reported (next round)", f"{d['seat_status'].eq('Not Reported').sum():,}")

if view.startswith("Closing"):
    keys = ["counselling", "year", "round_label", "quota_name", "institute", "inst_state", "college_type", "branch",
            "clinical_type", "degree", "allotted_cat"]
    d = d.assign(_surr=d["seat_status"].eq("Seat Surrendered"), _nr=d["seat_status"].eq("Not Reported"))
    g = d.groupby(keys, dropna=False, observed=True).agg(
        opening=("rank", "min"), closing=("rank", "max"), allotted=("rank", "size"),
        surrendered=("_surr", "sum"), not_reported=("_nr", "sum"))
    t = g.reset_index().sort_values(["year", "closing"], ascending=[False, True])
else:
    t = d[["counselling", "year", "round_label", "rank", "quota_name", "institute", "inst_state", "college_type",
           "branch", "clinical_type", "degree", "allotted_cat", "candidate_cat", "remarks", "seat_status",
           "prev_seat", "prev_status"]].rename(columns={"seat_status": "status of this seat (next round)",
                                                        "prev_seat": "seat held in previous round",
                                                        "prev_status": "previous seat status"})
    t = t.sort_values(["year", "rank"], ascending=[False, True])

st.caption(f"{len(t):,} rows" + (" (showing first 5,000 - download for all)" if len(t) > 5000 else ""))
st.dataframe(t.head(5000), hide_index=True, width="stretch", height=620)
st.download_button("⬇️ Download filtered data (CSV)", t.to_csv(index=False).encode(), "neetpg_filtered.csv", "text/csv")
