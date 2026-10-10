"""Household water usage tracker: log daily use by activity, see trends and a daily target."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db

try:  # the entry file (water_app.py) already sets it
    st.set_page_config(page_title="Water Usage Tracker", layout="wide")
except Exception:
    pass
db.init()

# Typical litres per use, for quick logging. Rough averages; let users edit the amount.
PRESETS = {
    "Shower (10 min)": 90, "Bucket bath": 20, "Toilet flush": 6, "Brushing teeth": 2,
    "Washing clothes (machine load)": 60, "Washing clothes (by hand)": 40,
    "Dishwashing": 25, "Cooking and drinking": 10, "Garden / plants": 30,
    "Vehicle washing": 60, "Other": 0,
}
WHO_MIN_L_PER_PERSON = 50    # WHO: roughly 50-100 L/person/day covers basic needs
DEFAULT_TARGET = 135         # India's CPHEEO urban norm, litres per capita per day (confirm for your city)

st.title("Water Usage Tracker")

with st.sidebar:
    st.header("Household")
    people = st.number_input("People in household", 1, 30, 4)
    target_pp = st.number_input("Target (L per person per day)", 20, 500, DEFAULT_TARGET)
daily_target = people * target_pp

left, right = st.columns([1, 2])
with left:
    st.subheader("Log usage")
    # Not a st.form: forms cannot react to the activity dropdown, so the preset would never fill in.
    def _apply_preset():
        st.session_state["litres_each"] = float(PRESETS[st.session_state["act"]])

    st.session_state.setdefault("litres_each", float(PRESETS["Shower (10 min)"]))
    d = st.date_input("Date", date.today(), max_value=date.today())
    cat = st.selectbox("Activity", list(PRESETS), key="act", on_change=_apply_preset)
    times = st.number_input("Times / loads", 1, 100, 1)
    litres_each = st.number_input("Litres each", 0.0, 5000.0, key="litres_each",
                                  help="Auto-fills a typical value; change it if you know your actual figure.")
    note = st.text_input("Note (optional)")
    ok = st.button("Add")
    if ok:
        total = times * litres_each
        if total <= 0:
            st.error("Amount must be greater than zero.")
        else:
            db.execute("INSERT INTO usage_logs (log_date, category, litres, note) VALUES (?,?,?,?)",
                       (d.isoformat(), cat, total, note or None))
            st.success(f"Logged {total:.0f} L.")

df = db.read("SELECT id, log_date, category, litres, note FROM usage_logs ORDER BY log_date DESC, id DESC")

with right:
    if df.empty:
        st.info("No usage logged yet. Add your first entry on the left.")
    else:
        df["log_date"] = pd.to_datetime(df["log_date"])
        today = pd.Timestamp(date.today())
        today_l = df.loc[df.log_date == today, "litres"].sum()
        week = df[df.log_date > today - pd.Timedelta(days=7)]
        days_logged = week.log_date.nunique()
        week_avg = week.litres.sum() / days_logged if days_logged else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("Today", f"{today_l:.0f} L", f"{today_l - daily_target:+.0f} vs target", delta_color="inverse")
        m2.metric("7-day average (logged days)", f"{week_avg:.0f} L/day")
        m3.metric("Per person today", f"{today_l / people:.0f} L")
        st.progress(min(today_l / daily_target, 1.0), text=f"{today_l / daily_target:.0%} of daily target ({daily_target:.0f} L)")
        if today_l > daily_target:
            st.warning("You are over today's target. The biggest category today: "
                       + df[df.log_date == today].groupby("category").litres.sum().idxmax())

        # Daily series with zero-filled gaps so the chart is honest about missing days.
        daily = df.groupby("log_date").litres.sum()
        full = pd.date_range(daily.index.min(), today)
        daily = daily.reindex(full, fill_value=0)
        st.subheader("Daily usage (last 30 days)")
        st.bar_chart(daily.tail(30))
        st.subheader("Where the water goes (last 30 days)")
        last30 = df[df.log_date > today - pd.Timedelta(days=30)]
        st.bar_chart(last30.groupby("category").litres.sum().sort_values(ascending=False))

        st.subheader("Entries")
        view = df.assign(log_date=df.log_date.dt.date)
        st.dataframe(view, use_container_width=True)
        c1, c2 = st.columns(2)
        c1.download_button("Download CSV", view.to_csv(index=False), "usage.csv", "text/csv")
        del_id = c2.number_input("Delete entry by id", 0, int(df.id.max()), 0)
        if c2.button("Delete") and del_id:
            db.execute("DELETE FROM usage_logs WHERE id = ?", (int(del_id),))
            st.rerun()
