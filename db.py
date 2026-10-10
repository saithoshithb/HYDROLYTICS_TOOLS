"""Tiny SQLite layer shared by all pages. No server needed.

NOTE: on free hosts (Streamlit Community Cloud, Render free) the disk is wiped on
restart. For a demo that is fine; for real use point WATER_DB at a persistent
volume or swap this module for Supabase/Postgres (same function names).
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

DB_PATH = os.environ.get("WATER_DB", "water_app.db")
UPLOAD_DIR = os.environ.get("WATER_UPLOADS", "uploads")

SCHEMA = """
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    location TEXT NOT NULL,
    description TEXT NOT NULL,
    contact TEXT,
    photo_path TEXT,
    status TEXT NOT NULL DEFAULT 'Open',
    admin_note TEXT
);
CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    category TEXT NOT NULL,
    litres REAL NOT NULL CHECK (litres >= 0),
    note TEXT
);
CREATE TABLE IF NOT EXISTS supply_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL UNIQUE,          -- 'YYYY-MM'
    supplied_kl REAL NOT NULL CHECK (supplied_kl > 0),
    billed_kl REAL NOT NULL CHECK (billed_kl >= 0),
    note TEXT
);
"""


@contextmanager
def connect():
    c = sqlite3.connect(DB_PATH, timeout=10)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with connect() as c:
        c.executescript(SCHEMA)
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read(sql, params=()):
    with connect() as c:
        return pd.read_sql_query(sql, c, params=params)


def execute(sql, params=()):
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def ticket(id_):
    return f"SAN-{int(id_):04d}"


def parse_ticket(text):
    t = text.strip().upper().replace("SAN-", "")
    return int(t) if t.isdigit() else None
