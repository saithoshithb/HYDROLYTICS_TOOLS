"""Sanitation complaints: citizens file, track; staff update status."""
import os
import uuid

import streamlit as st

import db

try:  # the entry file (water_app.py) already sets it
    st.set_page_config(page_title="Sanitation Complaints", layout="wide")
except Exception:
    pass
db.init()

CATEGORIES = ["Overflowing drain / sewage", "Dirty or contaminated water", "Public toilet unclean",
              "Garbage near water source", "Burst / leaking pipe", "No water supply", "Other"]
SEVERITY = ["Low", "Medium", "High", "Emergency"]
STATUS = ["Open", "In progress", "Resolved", "Rejected"]
MAX_PHOTO_MB = 5

# Staff password comes from the environment / Streamlit secrets, never hard-coded in the repo.
def get_admin_password():
    if os.environ.get("ADMIN_PASSWORD"):
        return os.environ["ADMIN_PASSWORD"]
    try:                                   # st.secrets raises if no secrets.toml exists
        return st.secrets.get("ADMIN_PASSWORD", "")
    except Exception:
        return ""


ADMIN_PASSWORD = get_admin_password()

st.title("Sanitation Complaints")
tab_new, tab_track, tab_admin = st.tabs(["File a complaint", "Track a complaint", "Staff dashboard"])

with tab_new:
    with st.form("complaint", clear_on_submit=True):
        c1, c2 = st.columns(2)
        category = c1.selectbox("Issue type", CATEGORIES)
        severity = c2.selectbox("Severity", SEVERITY, index=1)
        location = st.text_input("Location / landmark *", max_chars=200)
        description = st.text_area("What is the problem? *", max_chars=1000)
        contact = st.text_input("Phone or email (optional, for updates)", max_chars=100)
        photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"])
        sent = st.form_submit_button("Submit complaint")
    if sent:
        if not location.strip() or not description.strip():
            st.error("Location and description are required.")
        elif photo is not None and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            st.error(f"Photo is larger than {MAX_PHOTO_MB} MB.")
        else:
            path = None
            if photo is not None:
                ext = photo.name.rsplit(".", 1)[-1].lower()
                path = os.path.join(db.UPLOAD_DIR, f"{uuid.uuid4().hex}.{ext}")  # never trust user filename
                with open(path, "wb") as f:
                    f.write(photo.getbuffer())
            new_id = db.execute(
                "INSERT INTO complaints (created_at, category, severity, location, description, contact, photo_path)"
                " VALUES (?,?,?,?,?,?,?)",
                (db.now(), category, severity, location.strip(), description.strip(), contact.strip() or None, path))
            st.success(f"Complaint registered. Your ticket number is **{db.ticket(new_id)}**. Save it to track progress.")
            if severity == "Emergency":
                st.warning("For sewage overflow or contamination that threatens health, also call your local "
                           "municipal helpline.")

with tab_track:
    t = st.text_input("Ticket number (e.g. SAN-0001)")
    if t:
        cid = db.parse_ticket(t)
        row = db.read("SELECT * FROM complaints WHERE id = ?", (cid,)) if cid else None
        if row is None or row.empty:
            st.error("No complaint found with that ticket number.")
        else:
            r = row.iloc[0]
            st.subheader(f"{db.ticket(r.id)}: {r.status}")
            st.write(f"**{r.category}** at {r.location} (severity {r.severity}, filed {r.created_at})")
            st.write(r.description)
            if r.admin_note:
                st.info(f"Staff note: {r.admin_note}")
            if r.photo_path and os.path.exists(r.photo_path):
                st.image(r.photo_path, width=300)

with tab_admin:
    if not ADMIN_PASSWORD:
        st.info("Staff dashboard is disabled. Set the ADMIN_PASSWORD environment variable or Streamlit secret.")
    elif st.text_input("Staff password", type="password") != ADMIN_PASSWORD:
        st.caption("Enter the staff password to manage complaints.")
    else:
        df = db.read("SELECT id, created_at, category, severity, location, status, admin_note FROM complaints "
                     "ORDER BY CASE severity WHEN 'Emergency' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, id DESC")
        if df.empty:
            st.info("No complaints yet.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total", len(df))
            m2.metric("Open", int((df.status == "Open").sum()))
            m3.metric("Resolved", int((df.status == "Resolved").sum()))
            flt = st.multiselect("Filter by status", STATUS, default=["Open", "In progress"])
            view = df[df.status.isin(flt)] if flt else df
            st.dataframe(view.assign(ticket=view.id.map(db.ticket)).drop(columns="id"), use_container_width=True)
            st.download_button("Download all (CSV)", df.to_csv(index=False), "complaints.csv", "text/csv")
            st.divider()
            sel = st.selectbox("Update complaint", df.id.map(db.ticket))
            new_status = st.selectbox("New status", STATUS)
            note = st.text_input("Note to citizen")
            if st.button("Save update"):
                db.execute("UPDATE complaints SET status = ?, admin_note = ? WHERE id = ?",
                           (new_status, note or None, db.parse_ticket(sel)))
                st.success("Updated.")
                st.rerun()
