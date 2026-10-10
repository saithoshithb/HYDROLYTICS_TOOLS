"""Entry point for the water-sustainability modules only
(sanitation complaints, water usage tracker, leakage check).

Run locally:   python -m streamlit run water_app.py
Deploy:        set "Main file path" to water_app.py on share.streamlit.io
"""
import streamlit as st

st.set_page_config(page_title="Clean Water App", layout="wide")

pages = [
    st.Page("pages/sanitation_complaints.py", title="Sanitation Complaints", default=True),
    st.Page("pages/water_usage_tracker.py", title="Water Usage Tracker"),
    st.Page("pages/leakage_check.py", title="Leakage Check"),
]
st.navigation(pages).run()
