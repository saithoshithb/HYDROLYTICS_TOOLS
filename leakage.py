"""Leakage / non-revenue-water logic. Pure functions, no Streamlit or DB imports,
so they can be unit-tested on their own.

Units: supplied/billed in kilolitres (kL). 1 kL = 1000 L = 1 m3.

Core idea (water-balance method)
    supplied  = water the utility put into the network (bulk/inlet meter)
    billed    = water customers were charged for (sum of consumer meters)
    loss      = supplied - billed          (non-revenue water, NRW)
    loss_pct  = loss / supplied * 100

NRW is NOT all leakage. It also contains metering under-registration, theft,
unbilled authorised use (fire fighting, flushing) and billing errors. The app
therefore says "possible leakage", never "confirmed leakage".
"""
from dataclasses import dataclass

import pandas as pd

# Tunable. ~15-20% NRW is commonly treated as acceptable for Indian urban utilities;
# above 30% is high. Confirm the benchmark your team wants to cite.
WARN_PCT = 20.0
CRITICAL_PCT = 30.0


@dataclass
class Balance:
    supplied: float
    billed: float
    loss: float
    loss_pct: float
    level: str       # ok / warning / critical / invalid
    message: str


def water_balance(supplied_kl, billed_kl, warn=WARN_PCT, critical=CRITICAL_PCT):
    if supplied_kl is None or supplied_kl <= 0:
        return Balance(supplied_kl or 0, billed_kl or 0, 0, 0, "invalid",
                       "Supplied volume must be greater than zero.")
    if billed_kl < 0:
        return Balance(supplied_kl, billed_kl, 0, 0, "invalid", "Billed volume cannot be negative.")
    loss = supplied_kl - billed_kl
    pct = loss / supplied_kl * 100
    if loss < 0:
        # Billed > supplied is physically impossible in a closed network.
        return Balance(supplied_kl, billed_kl, loss, pct, "invalid",
                       "Billed volume is higher than supplied. Check for a faulty bulk meter, "
                       "wrong period, or a data-entry error.")
    if pct >= critical:
        level, msg = "critical", f"{pct:.1f}% of supplied water is unaccounted for. Likely major leakage or meter faults."
    elif pct >= warn:
        level, msg = "warning", f"{pct:.1f}% is unaccounted for, above the {warn:.0f}% benchmark."
    else:
        level, msg = "ok", f"{pct:.1f}% unaccounted for, within the {warn:.0f}% benchmark."
    return Balance(supplied_kl, billed_kl, loss, pct, level, msg)


def monthly_table(df):
    """df columns: period, supplied_kl, billed_kl. Returns df plus loss columns and a flag."""
    if df.empty:
        return df.assign(loss_kl=[], loss_pct=[], level=[])
    out = df.sort_values("period").copy()
    out["loss_kl"] = out["supplied_kl"] - out["billed_kl"]
    out["loss_pct"] = (out["loss_kl"] / out["supplied_kl"] * 100).round(1)
    out["level"] = [water_balance(s, b).level for s, b in zip(out.supplied_kl, out.billed_kl)]
    # Spike detection needs history: compare with the median of previous months.
    prev_med = out["loss_pct"].expanding().median().shift(1)
    out["spike"] = (out["loss_pct"] - prev_med) > 10
    return out


def household_check(logged_litres, billed_kl, tolerance_pct=15.0):
    """Compare what the household tracked itself against the bill.

    logged_litres: total from the usage tracker for the SAME billing period.
    Returns (level, message). Only meaningful if the user logged consistently.
    """
    if billed_kl <= 0:
        return "invalid", "Billed volume must be greater than zero."
    logged_kl = logged_litres / 1000
    gap_pct = (billed_kl - logged_kl) / billed_kl * 100
    if gap_pct > tolerance_pct:
        return "warning", (f"You billed {billed_kl:.1f} kL but logged only {logged_kl:.1f} kL "
                           f"({gap_pct:.0f}% gap). Possible hidden leak (toilet, pipe, tank overflow), "
                           "faulty meter, or unlogged usage.")
    if gap_pct < -tolerance_pct:
        return "info", (f"You logged more ({logged_kl:.1f} kL) than you were billed ({billed_kl:.1f} kL). "
                        "Your logging may double count, or the meter under-reads.")
    return "ok", "Your logged usage matches the bill within tolerance."


def night_flow_check(reading_start, reading_end, hours, threshold_l_per_h=2.0):
    """Classic leak test: close every tap, note the meter, wait, note again.
    Readings in litres. Any steady flow means a leak downstream of the meter."""
    if hours <= 0:
        return "invalid", "Hours must be greater than zero."
    used = reading_end - reading_start
    if used < 0:
        return "invalid", "End reading is lower than start reading (meter rollover or typo)."
    rate = used / hours
    if rate > threshold_l_per_h:
        return "warning", (f"{used:.0f} L flowed in {hours:g} h with everything off "
                           f"({rate:.1f} L/h). That indicates a leak.")
    return "ok", f"Flow was {rate:.1f} L/h, which is within meter noise. No leak indicated."
