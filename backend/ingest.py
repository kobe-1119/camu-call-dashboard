"""CSV ingestion module — reads raw call CSVs, classifies, and stores in SQLite."""
import pandas as pd
import re
from datetime import datetime
from .classifier import classify, parse_transcript
from .database import get_db

WORKFLOW_GROUPS = {
    "260310_AWV_DM_General": "AWV/DM General",
}

WORKFLOW_PREFIXES = [
    ("Diabetes", "Diabetes Templates"),
    ("AWV - Template", "AWV Templates"),
    ("Appointment Reminder", "Appointment Reminders"),
    ("No-Show/Cancel", "No-Show/Cancel Recall"),
    ("Insurance", "Insurance Updates"),
]


def get_workflow_group(workflow_name: str) -> str:
    if not workflow_name:
        return "Other"
    wf = workflow_name.strip()
    if wf in WORKFLOW_GROUPS:
        return WORKFLOW_GROUPS[wf]
    for prefix, group in WORKFLOW_PREFIXES:
        if wf.startswith(prefix):
            return group
    return "Other"


def parse_duration(dur_str: str) -> int:
    """Parse '1m 23s' or '45s' to total seconds."""
    if not dur_str or pd.isna(dur_str):
        return 0
    dur_str = str(dur_str).strip()
    minutes = 0
    seconds = 0
    m = re.search(r'(\d+)\s*m', dur_str)
    if m:
        minutes = int(m.group(1))
    s = re.search(r'(\d+)\s*s', dur_str)
    if s:
        seconds = int(s.group(1))
    return minutes * 60 + seconds


def parse_call_datetime(dt_str: str):
    """Parse 'March 12, 2026, 05:35 PM' -> (datetime_obj, date_str, hour)."""
    if not dt_str or pd.isna(dt_str):
        return None, None, None
    dt_str = str(dt_str).strip()
    try:
        dt = datetime.strptime(dt_str, "%B %d, %Y, %I:%M %p")
        return dt.isoformat(), dt.strftime("%Y-%m-%d"), dt.hour
    except ValueError:
        try:
            dt = datetime.strptime(dt_str, "%B %d, %Y, %I:%M %p")
            return dt.isoformat(), dt.strftime("%Y-%m-%d"), dt.hour
        except ValueError:
            return dt_str, None, None


def generate_summary(row: dict, outcome: str, sub_category: str) -> str:
    """Generate a concise AI-style summary of the call."""
    patient = row.get("Patient Name", "Unknown")
    workflow = row.get("Workflow Name", "")
    transcript = str(row.get("Transcript", ""))

    user_text, agent_text, user_words, _, turns = parse_transcript(transcript)

    if user_words == 0:
        return f"Call to {patient} — no patient response. Outcome: {outcome}."

    # Build a brief summary from key elements
    parts = []
    parts.append(f"Agent called from Vantage Medical Associates")

    if "diabetes" in agent_text.lower():
        parts.append("to check in about diabetes care")
    elif "appointment" in agent_text.lower() or "cita" in agent_text.lower():
        parts.append("regarding an appointment")
    elif "annual" in agent_text.lower() or "wellness" in agent_text.lower():
        parts.append("regarding an annual wellness visit")

    # Outcome-specific detail
    if outcome == "Accepted appointment":
        parts.append(f"Patient accepted the appointment")
    elif outcome == "Rejected appointment":
        parts.append(f"Patient declined. Reason: {sub_category}")
    elif outcome == "Voicemail left":
        parts.append(f"Reached voicemail ({sub_category})")
    elif outcome == "Requested callback":
        parts.append(f"Patient requested a callback")
    elif "No answer" in outcome:
        parts.append("No meaningful patient response")
    elif "Language barrier" in outcome:
        parts.append("Language barrier encountered")
    else:
        parts.append(f"Outcome: {outcome}")

    # Add a snippet of what patient said if relevant
    if user_words > 3 and outcome not in ("Voicemail left",):
        snippet = user_text[:200]
        parts.append(f'Said: "{snippet}"')

    return ". ".join(parts) + "."


def ingest_file(filepath: str) -> dict:
    """Ingest a raw call CSV or XLSX file into the database. Returns stats."""
    if filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        df = pd.read_excel(filepath, dtype=str, engine='openpyxl')
    else:
        df = pd.read_csv(filepath, dtype=str)
    df.columns = df.columns.str.strip()

    db = get_db()
    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        row_dict = row.to_dict()

        # Check for duplicate by EHR + datetime
        ehr_id = str(row_dict.get("Patient EHR ID", "")).strip()
        dt_raw = str(row_dict.get("Date & Time", "")).strip()
        if ehr_id and dt_raw:
            existing = db.execute(
                "SELECT id FROM calls WHERE patient_ehr_id = ? AND call_datetime LIKE ?",
                (ehr_id, parse_call_datetime(dt_raw)[0] or "")
            ).fetchone()
            if existing:
                skipped += 1
                continue

        outcome, sub_category = classify(row_dict)
        summary = generate_summary(row_dict, outcome, sub_category)
        dt_iso, date_str, hour = parse_call_datetime(dt_raw)
        duration_secs = parse_duration(row_dict.get("Duration", ""))
        wf_group = get_workflow_group(row_dict.get("Workflow Name", ""))

        db.execute("""
            INSERT INTO calls (
                patient_name, patient_ehr_id, from_number, to_number,
                call_datetime, call_date, call_hour, duration_seconds, duration_display,
                workflow_name, workflow_group, workflow_task,
                appointment_booked, in_voicemail, transcript,
                outcome, sub_category, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row_dict.get("Patient Name", ""),
            ehr_id,
            row_dict.get("From Number", ""),
            row_dict.get("To Number", ""),
            dt_iso, date_str, hour, duration_secs,
            row_dict.get("Duration", ""),
            row_dict.get("Workflow Name", ""),
            wf_group,
            row_dict.get("Workflow Task Name", ""),
            row_dict.get("Appointment Booked", ""),
            row_dict.get("In Voicemail", ""),
            row_dict.get("Transcript", ""),
            outcome, sub_category, summary
        ))
        inserted += 1

    db.commit()
    db.close()
    return {"inserted": inserted, "skipped": skipped, "total": len(df)}
