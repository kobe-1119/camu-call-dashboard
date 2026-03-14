"""SQLite database setup and access."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "calls.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        patient_ehr_id TEXT,
        from_number TEXT,
        to_number TEXT,
        call_datetime TEXT,
        call_date TEXT,
        call_hour INTEGER,
        duration_seconds INTEGER,
        duration_display TEXT,
        workflow_name TEXT,
        workflow_group TEXT,
        workflow_task TEXT,
        appointment_booked TEXT,
        in_voicemail TEXT,
        transcript TEXT,
        outcome TEXT,
        sub_category TEXT,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(call_date);
    CREATE INDEX IF NOT EXISTS idx_calls_group ON calls(workflow_group);
    CREATE INDEX IF NOT EXISTS idx_calls_outcome ON calls(outcome);
    CREATE INDEX IF NOT EXISTS idx_calls_ehr ON calls(patient_ehr_id);
    """)
    conn.commit()
    conn.close()
