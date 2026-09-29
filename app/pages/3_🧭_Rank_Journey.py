import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import data  # noqa: E402
from core.ui import not_ready, setup  # noqa: E402

setup("Rank journey", "🧭")
if not data.data_ready():
    not_ready()

st.title("🧭 What happened to people near my rank?")
st.caption("MCC (All India) round-by-round journey of every rank: Round 1 seat → status → Round 2 → Round 3 → stray.")
j = data.journeys()
prof = st.session_state.get("profile", {})
c1, c2, c3 = st.columns(3)
rank = c1.number_input("Rank", 1, 300000, int(prof.get("rank", 71385)))
width = c2.number_input("± window", 50, 20000, 1000, step=250)
year = c3.selectbox("Year", sorted(j["year"].unique(), reverse=True))
d = j[(j["year"] == year) & (j["rank"].between(rank - width, rank + width))]
cat = st.multiselect("Category", sorted(x for x in d["category"].unique() if x))
if cat:
    d = d[d["category"].isin(cat)]
st.caption(f"{len(d):,} candidates between ranks {rank - width:,} and {rank + width:,} in {year} (only candidates who "
           f"appear in the Round 3 result list).")
st.dataframe(d.drop(columns=["year"]).rename(columns={
    "r1_seat": "Round 1 seat", "r1_status": "R1 status", "r2_seat": "Round 2 seat", "r2_status": "R2 status",
    "r3_seat": "Round 3 seat", "r3_remarks": "R3 remarks", "stray_seat": "Stray seat",
    "special_stray_seat": "Special stray seat"}), hide_index=True, width="stretch", height=650)
