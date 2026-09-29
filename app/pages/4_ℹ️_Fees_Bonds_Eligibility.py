import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import data  # noqa: E402
from core.ui import setup  # noqa: E402

setup("Fees, bonds & eligibility", "ℹ️")
st.title("ℹ️ Fees, bonds, stipends & eligibility")
st.warning("Fee / bond / stipend figures are **indicative**, compiled from aggregator sites and official prospectuses "
           "(sources in the last column). They change every year and sources sometimes disagree - always confirm in "
           "the current year's official prospectus / MCC information bulletin before choice filling.")

t1, t2, t3 = st.tabs(["🏛️ State govt colleges: bond & stipend", "💰 Deemed university fees", "✅ Eligibility rules"])
with t1:
    st.dataframe(data.policy(), hide_index=True, width="stretch", height=620)
with t2:
    df = data.deemed_fees().copy()
    df["Fee range (₹ lakh / yr)"] = (df["annual_fee_min"] / 1e5).round(1).astype(str) + " – " + \
                                    (df["annual_fee_max"] / 1e5).round(1).astype(str)
    st.caption("Range across all branches (clinical branches like Radiology / Dermatology are at the top end).")
    st.dataframe(df[["college", "state", "Fee range (₹ lakh / yr)", "source"]], hide_index=True,
                 width="stretch", height=620)
with t3:
    st.markdown("""
### MCC (All India) — anyone who qualified NEET PG
* **All India Quota (50% of state govt seats + central institutes)**, **DNB**, **Deemed universities** — open to all.
* **Central university internal quotas** (DU, IP University, BHU, AMU) — only for MBBS graduates of that university.
* **NRI, Armed Forces, Muslim / Jain minority, ESI** — only for those specific candidates.

### Bihar state quota — BCECEB PGMAC ([prospectus 2025](https://bceceboard.bihar.gov.in/pdf_Pros/PROS_PGMAC25.pdf))
* Clause 6.1(i): **MBBS must be from a medical college in Bihar** (govt or private). A Bihar domicile who did MBBS
  outside Bihar is **not** eligible for Bihar state-quota govt seats.
* Reservation (EWS / BC / EBC / SC / ST / RCG women) applies only to Bihar domiciles; others compete as UR.
* Private-college seats: rules modified by Annexure-5 (scanned, Hindi) — the app shows Bihar private management
  seats as **"verify eligibility"** for non-Bihar MBBS graduates. Confirm with BCECEB.

### Odisha state quota — DMET PGMCC ([guidelines 2025](https://dmetodisha.in/PGMCC_Static/DOWNLOADSPGM_22/Guidelines_PG_Medical_2025%20FINAL.pdf))
* Section F.1: **permanent resident of Odisha**, **or** an out-of-state candidate who did MBBS in an
  **Odisha Govt medical college under the 15% All India Quota**. Private-college MBBS from outside Odisha is not eligible.
* Covers state-quota seats in Odisha govt colleges and **all seats (incl. management) of Hi-Tech Bhubaneswar & Rourkela**.
* Seats split 50:50 between **Direct** and **In-service** candidates. Management seats are UR only. OBC is merged into UR.
* Govt college fee ≈ ₹35,000/yr tuition + small one-time fees. Leaving the seat: ₹10 lakh + stipend received.

### Not yet covered
Other states' quotas (UP, Jharkhand, West Bengal, …) can be added by downloading their result PDFs into
`data/raw/<state>/` and adding a parser in `pipeline/parse_states.py`.
""")
