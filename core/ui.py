"""Small shared UI helpers: page setup, optional password gate, table styling."""
import os

import pandas as pd
import streamlit as st

CHANCE_COLORS = {"High": "#1b7f3b", "Good": "#4caf50", "Borderline": "#f0a202", "Low (reach)": "#e4572e",
                 "Stray only": "#8e7cc3"}


def setup(title, icon="🩺"):
    st.set_page_config(page_title=f"{title} · NEET PG Counselling", page_icon=icon, layout="wide")
    _gate()


def _gate():
    """If APP_PASSWORD (env) or st.secrets['password'] is set, require it once per session."""
    pwd = os.environ.get("APP_PASSWORD")
    try:
        pwd = pwd or st.secrets.get("password")
    except Exception:
        pass
    if not pwd or st.session_state.get("authed"):
        return
    st.title("🔒 Private tool")
    if st.text_input("Password", type="password") == pwd:
        st.session_state["authed"] = True
        st.rerun()
    st.stop()


def style_chance(df: pd.DataFrame):
    def color(v):
        c = CHANCE_COLORS.get(v)
        return f"background-color:{c};color:white;font-weight:600" if c else ""
    if "Chance" in df.columns:
        return df.style.map(color, subset=["Chance"])
    return df


def not_ready():
    st.error("Processed data not found. Run the data pipeline first:\n\n"
             "```\npython pipeline/parse_mcc.py\npython pipeline/parse_states.py\n"
             "python pipeline/parse_nmc.py\npython pipeline/build.py\n```")
    st.stop()
