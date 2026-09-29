"""Cached data loaders for the Streamlit app."""
import os

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
REFERENCE = os.path.join(ROOT, "data", "reference")

INDIAN_STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
                 "Chhattisgarh", "Dadra and Nagar Haveli", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
                 "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra",
                 "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
                 "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]


@st.cache_data(show_spinner="Loading allotment data ...")
def allotments():
    return pd.read_parquet(os.path.join(PROCESSED, "allotments.parquet"))


@st.cache_data(show_spinner="Loading closing ranks ...")
def closing():
    return pd.read_parquet(os.path.join(PROCESSED, "closing.parquet"))


@st.cache_data
def journeys():
    return pd.read_parquet(os.path.join(PROCESSED, "journeys.parquet"))


@st.cache_data
def seat_matrix():
    return pd.read_parquet(os.path.join(PROCESSED, "seat_matrix_2026.parquet"))


@st.cache_data
def policy():
    return pd.read_csv(os.path.join(REFERENCE, "state_policy.csv"))


@st.cache_data
def deemed_fees():
    return pd.read_csv(os.path.join(REFERENCE, "deemed_fees.csv"))


@st.cache_data
def institute_map():
    path = os.path.join(PROCESSED, "institute_map.parquet")
    return pd.read_parquet(path) if os.path.exists(path) else None


def data_ready():
    return os.path.exists(os.path.join(PROCESSED, "closing.parquet"))
