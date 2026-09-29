@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\streamlit.exe (
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\streamlit run app\Home.py
