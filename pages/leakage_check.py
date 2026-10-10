"""Leakage check: supplied vs billed water balance, household bill check, night-flow test."""
import pandas as pd
import streamlit as st

import db
import leakage as lk

try:  # the entry file (water_app.py) already sets it
    st.set_page_config(page_title="Leakage Check", layout="wide")
except Exception:
    pass
db.init()

st.title("Water Leakage Check")
st.caption("Compares water supplied with water billed to estimate non-revenue water. "
           "A gap suggests possible leakage but can also come from meter errors, theft or unbilled use.")

tab_bal, tab_house, tab_night = st.tabs(["Supplied vs billed", "My bill vs my usage", "Night-flow leak test"])

with tab_bal:
    with st.sidebar:
        st.header("Thresholds")
        warn = st.number_input("Warning at loss % ≥", 1.0, 99.0, lk.WARN_PCT)
        crit = st.number_input("Critical at loss % ≥", 1.0, 99.0, lk.CRITICAL_PCT)
    if crit <= warn:
        st.error("Critical threshold must be higher than the warning threshold.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    period = c1.text_input("Month (YYYY-MM)", pd.Timestamp.today().strftime("%Y-%m"))
    supplied = c2.number_input("Supplied (kL)", 0.0, 1e9, 0.0, help="Bulk/inlet meter reading for the month. 1 kL = 1000 L.")
    billed = c3.number_input("Billed (kL)", 0.0, 1e9, 0.0, help="Sum of consumer meter volumes on the bill.")
    note = st.text_input("Note (optional)")
    if st.button("Analyse and save"):
        valid_period = pd.to_datetime(period, format="%Y-%m", errors="coerce")
        bal = lk.water_balance(supplied, billed, warn, crit)
        if pd.isna(valid_period):
            st.error("Month must look like 2026-09.")
        elif bal.level == "invalid":
            st.error(bal.message)
        else:
            show = {"ok": st.success, "warning": st.warning, "critical": st.error}[bal.level]
            show(bal.message)
            m1, m2 = st.columns(2)
            m1.metric("Unaccounted water", f"{bal.loss:,.1f} kL")
            m2.metric("Loss", f"{bal.loss_pct:.1f}%")
            # INSERT OR REPLACE so re-entering a month corrects it instead of crashing on UNIQUE.
            db.execute("INSERT OR REPLACE INTO supply_bills (period, supplied_kl, billed_kl, note) VALUES (?,?,?,?)",
                       (period, supplied, billed, note or None))

    hist = db.read("SELECT period, supplied_kl, billed_kl FROM supply_bills")
    if not hist.empty:
        t = lk.monthly_table(hist)
        st.subheader("History")
        st.line_chart(t.set_index("period")[["supplied_kl", "billed_kl"]])
        st.bar_chart(t.set_index("period")["loss_pct"])
        flagged = t[t.spike]
        if not flagged.empty:
            st.warning("Sudden jump in loss compared with earlier months: " + ", ".join(flagged.period)
                       + ". A new burst or meter fault is possible.")
        st.dataframe(t, use_container_width=True)
        st.download_button("Download CSV", t.to_csv(index=False), "water_balance.csv", "text/csv")

with tab_house:
    st.write("Checks your own tracked usage (from the Usage Tracker page) against your bill for the same dates.")
    a, b = st.columns(2)
    start = a.date_input("Bill period start")
    end = b.date_input("Bill period end")
    billed_kl = st.number_input("Billed volume on your bill (kL)", 0.0, 1e6, 0.0, key="hb")
    if st.button("Compare"):
        if end < start:
            st.error("End date is before start date.")
        else:
            logs = db.read("SELECT log_date, litres FROM usage_logs WHERE log_date BETWEEN ? AND ?",
                           (start.isoformat(), end.isoformat()))
            days = (end - start).days + 1
            logged_days = logs.log_date.nunique()
            if logs.empty:
                st.info("No usage logged in that period.")
            else:
                if logged_days < 0.8 * days:
                    st.warning(f"You logged on only {logged_days} of {days} days, so the comparison is unreliable.")
                level, msg = lk.household_check(logs.litres.sum(), billed_kl)
                {"ok": st.success, "warning": st.warning, "info": st.info, "invalid": st.error}[level](msg)

with tab_night:
    st.write("1. Close every tap and stop all appliances.  2. Note the meter.  3. Wait 1-2 hours (overnight is best).  4. Note it again.")
    r1, r2, r3 = st.columns(3)
    s = r1.number_input("Start reading (L)", 0.0, 1e9, 0.0)
    e = r2.number_input("End reading (L)", 0.0, 1e9, 0.0)
    h = r3.number_input("Hours between", 0.0, 48.0, 1.0)
    st.caption("Many meters show kL (m³). Multiply by 1000 to enter litres.")
    if st.button("Check"):
        level, msg = lk.night_flow_check(s, e, h)
        {"ok": st.success, "warning": st.warning, "invalid": st.error}[level](msg)
