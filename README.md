# NEET PG Counselling Helper

Private Streamlit app that uses previous years' allotment data to predict which **college + branch** a NEET PG
rank can get, round by round. It puts **All India Quota first, then state quota**, and **Govt before private**.

## Run

```
run.bat                      (Windows: double-click)
# or
.venv\Scripts\streamlit run app\Home.py
```
Open http://localhost:8501. To add a password, set the environment variable `APP_PASSWORD` or put
`password = "..."` in `.streamlit/secrets.toml`.

## Pages
| Page | What it does |
|---|---|
| 🎯 Predictor (Home) | Enter rank, category, PwD, domicile, MBBS state / seat type and preferred branches. The page checks eligibility per counselling and quota, estimates each seat's 2026 closing rank and shows the chance (High / Good / Borderline / Reach / Stray only) and the round it is likely available from. It also lists fee / bond / stipend and a suggested choice-filling order. |
| 📊 Explore Data | Every allotment 2023-2025 (MCC + Bihar + Odisha). Filters: rank, year, round, quota, seat and candidate category, state, college type, branch, clinical / para / non-clinical, course type, remarks / status (Reported, Not Reported, Seat Surrendered, Upgraded ...). Download as CSV. |
| 📤 Upload Current Round | Upload a 2026 MCC (or Bihar) result PDF. It is parsed, shown with filters, compared seat-by-seat with the same round of previous years, and checked against your rank. |
| 🧭 Rank Journey | What candidates near a rank got in R1 → R2 → R3 → stray, with status at each step. |
| ℹ️ Fees, Bonds & Eligibility | State bond / stipend table, deemed-university fee ranges, eligibility rules with sources. |

## Data
* **MCC (mcc.nic.in)**: Round 1, 2, 3, Stray and Special Stray results for 2023, 2024 and 2025, plus the 2025 seat matrices.
* **Bihar (BCECEB PGMAC)**: 2023 all rounds, 2024 up to R3 + stray + special stray, 2025 R1-R3 + stray, 2025 prospectus.
* **Odisha (DMET PGMCC)**: 2025 R1, R1 upgrade, R2, final admitted list, merit list (to map to NEET AIR), 2025 guidelines.
* **NMC**: PG seat matrix for AY 2026-27 (Govt / Pvt / Deemed tag + seats).
* **Reference** (`data/reference/`): state bond / stipend and deemed fee ranges, taken from aggregator sites. These are indicative only; check them against the official documents.

Candidate names, phone numbers and payment references in the source PDFs are **not** stored.

## Rebuild / add data
```
.venv\Scripts\python pipeline\parse_mcc.py      # PDFs in data/raw/mcc/<year>/{R1,R2,R3,STRAY,SPSTRAY}.pdf
.venv\Scripts\python pipeline\parse_states.py   # data/raw/bihar, data/raw/odisha
.venv\Scripts\python pipeline\parse_nmc.py      # data/raw/nmc/seat_matrix_2026_27.pdf
.venv\Scripts\python pipeline\build.py          # -> data/processed/*.parquet
```
Once the 2026 results are published, drop them into `data/raw/mcc/2026/` with the same file names and rerun. The
predictor then weights 2026 above the older years (adjust `YEAR_WEIGHTS` in `core/predict.py`).

## How prediction works
For each seat group (college × branch × course type × quota × seat category) the app takes the closing rank in
every round of every year. The 2026 estimate is the deepest closing rank up to Round 3, averaged across years with
weights 2025 = 3, 2024 = 2, 2023 = 1. Chance is your rank ÷ that estimate: ≤ 0.85 High, ≤ 1.0 Good, ≤ 1.15 Borderline,
≤ 1.35 Reach. A seat you would have got in fewer than half of the years is capped at Borderline.
Seat counts and cutoffs shift every year, so these are estimates, not guarantees.
