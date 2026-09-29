import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from core import data  # noqa: E402
from core.mcc import ROUND_NO  # noqa: E402
from core.predict import allowed_categories, Profile  # noqa: E402
from core.ui import not_ready, setup  # noqa: E402
from core.upload import compare_with_history, parse_upload  # noqa: E402

setup("Upload current round", "📤")
if not data.data_ready():
    not_ready()

st.title("📤 Upload a current-year counselling document")
st.markdown("Upload an **MCC seat-allotment result PDF** (any round, e.g. from "
            "[mcc.nic.in → Current Events PG](https://mcc.nic.in/current-events-pg/)) or a **Bihar PGMAC result**. "
            "The app reads it, shows it with filters, and compares every seat's closing rank with the same round "
            "in previous years. Other PDFs (seat matrix, vacancy lists) are shown as plain tables.")

c1, c2 = st.columns(2)
year = c1.number_input("Counselling year", 2020, 2035, 2026)
rnd = c2.selectbox("Round (leave Auto for MCC results - it is detected)",
                   ["Auto", "R1", "R2", "R3", "R4", "STRAY", "SPSTRAY"])
up = st.file_uploader("PDF file", type=["pdf"])
if not up:
    st.stop()

key = f"{up.name}-{up.size}-{year}-{rnd}"
if st.session_state.get("upload_key") != key:
    bar = st.progress(0.0, text="Reading PDF ... (large MCC results can take a few minutes)")
    kind, df = parse_upload(up.getvalue(), int(year), "" if rnd == "Auto" else rnd,
                            progress=lambda f: bar.progress(f, text=f"Reading PDF ... {int(f * 100)}%"),
                            institute_map=data.institute_map())
    bar.empty()
    st.session_state.update(upload_key=key, upload_kind=kind, upload_df=df)
kind, df = st.session_state["upload_kind"], st.session_state["upload_df"]

if df is None or df.empty:
    st.error("Couldn't find any tables in this PDF (it may be a scanned image).")
    st.stop()

if kind == "table":
    st.info(f"Not an allotment result - showing the {len(df):,} table rows found.")
    q = st.text_input("Search")
    t = df[df.apply(lambda r: r.astype(str).str.contains(q, case=False).any(), axis=1)] if q else df
    st.dataframe(t, hide_index=True, width="stretch", height=600)
    st.download_button("⬇️ CSV", t.to_csv(index=False).encode(), "upload.csv", "text/csv")
    st.stop()

label = df["round"].iloc[0] if "round" in df else rnd
st.success(f"Read **{len(df):,} allotments** ({kind.upper()}, {year}, {label}).")

tabs = st.tabs(["📋 Allotments (filterable)", "📉 Compare with previous years", "🎯 Seats open at my rank"])
with tabs[0]:
    f1, f2, f3, f4 = st.columns(4)
    sel = {}
    for col, (c, name) in zip((f1, f2, f3, f4), (("branch", "Branch"), ("quota_name", "Quota"),
                                                ("inst_state", "State"), ("allotted_cat", "Seat category"))):
        if c in df:
            sel[c] = col.multiselect(name, sorted(x for x in df[c].dropna().unique() if x != ""))
    t = df
    for c, v in sel.items():
        if v:
            t = t[t[c].isin(v)]
    show = [c for c in ["rank", "quota_name", "institute", "inst_state", "college_type", "branch", "clinical_type",
                        "degree", "allotted_cat", "candidate_cat", "remarks", "prev_seat", "prev_status"] if c in t]
    st.dataframe(t[show].sort_values("rank"), hide_index=True, width="stretch", height=560)
    st.download_button("⬇️ CSV", t[show].to_csv(index=False).encode(), "uploaded_allotments.csv", "text/csv")

with tabs[1]:
    if kind != "mcc":
        st.info("Comparison is available for MCC results.")
    else:
        cmp = compare_with_history(df, data.closing(), ROUND_NO.get(label, 1))
        up_n = (cmp.get("change_vs_last_year", pd.Series(dtype=float)) > 0).sum()
        st.caption(f"Positive change = the seat went to a **higher (worse) rank** than last year, i.e. it got easier. "
                   f"{up_n:,} seat groups got easier, {(cmp.get('change_vs_last_year', pd.Series(dtype=float)) < 0).sum():,} got harder.")
        st.dataframe(cmp, hide_index=True, width="stretch", height=560)
        st.download_button("⬇️ CSV", cmp.to_csv(index=False).encode(), "comparison.csv", "text/csv")

with tabs[2]:
    prof = st.session_state.get("profile")
    if not prof:
        st.info("Fill in your details on the **Predictor** page first.")
    else:
        p = Profile(**prof)
        cats = allowed_categories(p, "MCC (All India)" if kind == "mcc" else "Bihar State")
        m = df[df["allotted_cat"].isin(cats) & (p.pwd | ~df["allotted_pwd"].astype(bool))]
        g = m.groupby(["quota_name", "institute", "inst_state", "college_type", "branch", "degree"])["rank"].max()
        g = g[g >= p.rank].rename("closing rank this round").reset_index().sort_values("closing rank this round")
        st.caption(f"Seat groups in this uploaded round whose last allotted rank was at or beyond your rank "
                   f"({p.rank:,}) for your categories {sorted(cats)} - i.e. you would have been in range.")
        st.dataframe(g, hide_index=True, width="stretch", height=560)
