"""FastAPI application with all dashboard API endpoints."""
import os
import tempfile
import math
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from .database import get_db, init_db
from .ingest import ingest_file

app = FastAPI(title="Camu Health Call Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTCOME_COLORS = {
    "Accepted appointment": "#C6EFCE",
    "Rejected appointment": "#FFC7CE",
    "Requested callback": "#FFEB9C",
    "Voicemail left": "#BDD7EE",
    "Other - No answer/Hangup": "#D9D9D9",
    "Other - Language barrier": "#E2EFDA",
    "Other - Wrong number/Deceased": "#F2DCDB",
    "Other - Engaged/Inconclusive": "#FCE4D6",
    "Other - Patient relocated": "#F2DCDB",
    "Other - Third party answered": "#FCE4D6",
    "Other - Inconclusive": "#D9D9D9",
}


@app.on_event("startup")
def startup():
    init_db()


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and ingest a raw call CSV or XLSX."""
    suffix = ".xlsx" if file.filename and file.filename.endswith(".xlsx") else ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = ingest_file(tmp_path)
        return result
    finally:
        os.unlink(tmp_path)


@app.get("/api/dates")
def get_dates():
    """Get all available dates."""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT call_date FROM calls WHERE call_date IS NOT NULL ORDER BY call_date DESC"
    ).fetchall()
    db.close()
    return [r["call_date"] for r in rows]


@app.get("/api/groups")
def get_groups():
    """Get all workflow groups with call counts."""
    db = get_db()
    rows = db.execute(
        "SELECT workflow_group, COUNT(*) as count FROM calls GROUP BY workflow_group ORDER BY count DESC"
    ).fetchall()
    db.close()
    return [{"group": r["workflow_group"], "count": r["count"]} for r in rows]


def _build_where(group: Optional[str], date: Optional[str]):
    """Build WHERE clause and params for group/date filtering."""
    clauses = []
    params = []
    if group and group != "All":
        clauses.append("workflow_group = ?")
        params.append(group)
    if date and date != "all":
        clauses.append("call_date = ?")
        params.append(date)
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


@app.get("/api/stats")
def get_stats(
    group: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
):
    """KPI aggregations: total calls, accepted, rejected, VM, callback, no answer, avg duration, conversion rate."""
    db = get_db()
    where, params = _build_where(group, date)

    row = db.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted,
            SUM(CASE WHEN outcome = 'Rejected appointment' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN outcome = 'Voicemail left' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN outcome = 'Requested callback' THEN 1 ELSE 0 END) as callback,
            SUM(CASE WHEN outcome LIKE 'Other - No answer%%' THEN 1 ELSE 0 END) as no_answer,
            AVG(duration_seconds) as avg_duration,
            COUNT(DISTINCT call_date) as num_days
        FROM calls WHERE {where}
    """, params).fetchone()

    total = row["total"] or 0
    accepted = row["accepted"] or 0
    conversion = round(accepted / total * 100, 1) if total > 0 else 0

    # Day-over-day delta (compare to previous day if specific date selected)
    delta = {}
    if date and date != "all":
        prev_row = db.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted
            FROM calls
            WHERE call_date = date(?, '-1 day')
            {"AND workflow_group = ?" if group and group != "All" else ""}
        """, [date] + ([group] if group and group != "All" else [])).fetchone()
        prev_total = prev_row["total"] or 0
        prev_accepted = prev_row["accepted"] or 0
        prev_conv = round(prev_accepted / prev_total * 100, 1) if prev_total > 0 else 0
        delta = {
            "total": total - prev_total,
            "accepted": accepted - prev_accepted,
            "conversion": round(conversion - prev_conv, 1),
        }

    result = {
        "total": total,
        "accepted": accepted,
        "rejected": row["rejected"] or 0,
        "voicemail": row["voicemail"] or 0,
        "callback": row["callback"] or 0,
        "no_answer": row["no_answer"] or 0,
        "avg_duration": round(row["avg_duration"] or 0, 1),
        "conversion_rate": conversion,
        "num_days": row["num_days"] or 0,
        "delta": delta,
        "outcomes": {},
        "sub_categories": {},
    }

    # Outcome breakdown
    outcomes = db.execute(f"""
        SELECT outcome, COUNT(*) as cnt FROM calls WHERE {where} GROUP BY outcome ORDER BY cnt DESC
    """, params).fetchall()
    result["outcomes"] = {r["outcome"]: r["cnt"] for r in outcomes}

    # Sub-category breakdown
    subs = db.execute(f"""
        SELECT sub_category, COUNT(*) as cnt FROM calls WHERE {where} GROUP BY sub_category ORDER BY cnt DESC
    """, params).fetchall()
    result["sub_categories"] = {r["sub_category"]: r["cnt"] for r in subs}

    db.close()
    return result


@app.get("/api/trends")
def get_trends(group: Optional[str] = Query(None)):
    """Daily trend data for charts."""
    db = get_db()
    group_clause = "AND workflow_group = ?" if group and group != "All" else ""
    group_params = [group] if group and group != "All" else []

    rows = db.execute(f"""
        SELECT
            call_date,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted,
            SUM(CASE WHEN outcome = 'Rejected appointment' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN outcome = 'Voicemail left' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN outcome = 'Requested callback' THEN 1 ELSE 0 END) as callback,
            SUM(CASE WHEN outcome LIKE 'Other - No answer%%' THEN 1 ELSE 0 END) as no_answer,
            SUM(CASE WHEN outcome LIKE 'Other%%' THEN 1 ELSE 0 END) as other,
            AVG(duration_seconds) as avg_duration
        FROM calls
        WHERE call_date IS NOT NULL {group_clause}
        GROUP BY call_date
        ORDER BY call_date
    """, group_params).fetchall()

    result = []
    for r in rows:
        total = r["total"]
        accepted = r["accepted"]
        result.append({
            "date": r["call_date"],
            "total": total,
            "accepted": accepted,
            "rejected": r["rejected"],
            "voicemail": r["voicemail"],
            "callback": r["callback"],
            "no_answer": r["no_answer"],
            "other": r["other"],
            "conversion_rate": round(accepted / total * 100, 1) if total > 0 else 0,
            "avg_duration": round(r["avg_duration"] or 0, 1),
        })
    db.close()
    return result


@app.get("/api/calls")
def get_calls(
    group: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """Paginated call details with search."""
    db = get_db()
    where, params = _build_where(group, date)

    if search:
        where += " AND (patient_name LIKE ? OR patient_ehr_id LIKE ? OR outcome LIKE ? OR sub_category LIKE ? OR summary LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s, s, s])

    # Count
    count_row = db.execute(f"SELECT COUNT(*) as cnt FROM calls WHERE {where}", params).fetchone()
    total_count = count_row["cnt"]

    # Fetch page
    offset = (page - 1) * per_page
    rows = db.execute(f"""
        SELECT id, patient_name, patient_ehr_id, from_number, to_number,
               call_datetime, call_date, call_hour, duration_seconds, duration_display,
               workflow_name, workflow_group, workflow_task,
               outcome, sub_category, summary
        FROM calls
        WHERE {where}
        ORDER BY call_datetime DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()

    db.close()
    return {
        "calls": [dict(r) for r in rows],
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total_count / per_page) if total_count > 0 else 0,
    }


@app.get("/api/followup")
def get_followup(group: Optional[str] = Query(None)):
    """Follow-up queue: callbacks with staleness tracking."""
    db = get_db()
    group_clause = "AND workflow_group = ?" if group and group != "All" else ""
    group_params = [group] if group and group != "All" else []

    rows = db.execute(f"""
        SELECT patient_name, patient_ehr_id, workflow_name, workflow_group,
               outcome, sub_category, summary, duration_display, call_date,
               julianday('now') - julianday(call_date) as days_ago
        FROM calls
        WHERE outcome = 'Requested callback' {group_clause}
        ORDER BY call_date DESC
    """, group_params).fetchall()

    result = []
    for r in rows:
        days = int(r["days_ago"]) if r["days_ago"] else 0
        if days <= 0:
            staleness = "fresh"
        elif days == 1:
            staleness = "aging"
        else:
            staleness = "stale"
        result.append({
            "patient_name": r["patient_name"],
            "ehr_id": r["patient_ehr_id"],
            "workflow": r["workflow_name"],
            "group": r["workflow_group"],
            "outcome": r["outcome"],
            "sub_category": r["sub_category"],
            "summary": r["summary"],
            "duration": r["duration_display"],
            "date": r["call_date"],
            "days_ago": days,
            "staleness": staleness,
        })

    db.close()
    return result


@app.get("/api/tod")
def get_time_of_day(group: Optional[str] = Query(None)):
    """Time-of-day analysis: calls and conversions by hour."""
    db = get_db()
    group_clause = "AND workflow_group = ?" if group and group != "All" else ""
    group_params = [group] if group and group != "All" else []

    rows = db.execute(f"""
        SELECT
            call_hour,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted
        FROM calls
        WHERE call_hour IS NOT NULL {group_clause}
        GROUP BY call_hour
        ORDER BY call_hour
    """, group_params).fetchall()

    result = []
    for r in rows:
        total = r["total"]
        accepted = r["accepted"]
        result.append({
            "hour": r["call_hour"],
            "total": total,
            "accepted": accepted,
            "conversion_rate": round(accepted / total * 100, 1) if total > 0 else 0,
        })

    db.close()
    return result


@app.get("/api/scripts")
def get_scripts(group: Optional[str] = Query(None)):
    """Script/template comparison: effectiveness by workflow task."""
    db = get_db()
    group_clause = "AND workflow_group = ?" if group and group != "All" else ""
    group_params = [group] if group and group != "All" else []

    rows = db.execute(f"""
        SELECT
            workflow_task,
            workflow_name,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted,
            SUM(CASE WHEN outcome = 'Rejected appointment' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN outcome = 'Voicemail left' THEN 1 ELSE 0 END) as voicemail,
            AVG(duration_seconds) as avg_duration
        FROM calls
        WHERE workflow_task IS NOT NULL AND workflow_task != '' {group_clause}
        GROUP BY workflow_task, workflow_name
        HAVING total >= 3
        ORDER BY total DESC
    """, group_params).fetchall()

    result = []
    for r in rows:
        total = r["total"]
        accepted = r["accepted"]
        result.append({
            "task": r["workflow_task"],
            "workflow": r["workflow_name"],
            "total": total,
            "accepted": accepted,
            "rejected": r["rejected"],
            "voicemail": r["voicemail"],
            "conversion_rate": round(accepted / total * 100, 1) if total > 0 else 0,
            "avg_duration": round(r["avg_duration"] or 0, 1),
        })

    db.close()
    return result


@app.get("/api/insights")
def get_insights(
    group: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
):
    """AI-generated action items and insights."""
    db = get_db()
    where, params = _build_where(group, date)

    row = db.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted,
            SUM(CASE WHEN outcome = 'Rejected appointment' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN outcome = 'Voicemail left' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN outcome = 'Requested callback' THEN 1 ELSE 0 END) as callback,
            SUM(CASE WHEN outcome LIKE 'Other - No answer%%' THEN 1 ELSE 0 END) as no_answer,
            SUM(CASE WHEN outcome = 'Other - Language barrier' THEN 1 ELSE 0 END) as language_barrier
        FROM calls WHERE {where}
    """, params).fetchone()

    total = row["total"] or 0
    if total == 0:
        db.close()
        return {"insights": [], "action_items": []}

    accepted = row["accepted"] or 0
    rejected = row["rejected"] or 0
    voicemail = row["voicemail"] or 0
    callback = row["callback"] or 0
    no_answer = row["no_answer"] or 0
    lang_barrier = row["language_barrier"] or 0

    conversion = round(accepted / total * 100, 1)
    vm_rate = round(voicemail / total * 100, 1)
    na_rate = round(no_answer / total * 100, 1)

    insights = []
    action_items = []

    # Conversion rate assessment
    if conversion > 30:
        insights.append({"type": "success", "text": f"Strong conversion rate at {conversion}% — well above target."})
    elif conversion > 15:
        insights.append({"type": "info", "text": f"Moderate conversion rate at {conversion}%. Room for improvement."})
    elif conversion > 5:
        insights.append({"type": "warning", "text": f"Low conversion rate at {conversion}%. Review call scripts and timing."})
    else:
        insights.append({"type": "danger", "text": f"Very low conversion rate at {conversion}%. Immediate attention needed."})

    # Voicemail rate
    if vm_rate > 40:
        insights.append({"type": "warning", "text": f"High voicemail rate ({vm_rate}%). Consider adjusting call times."})
        action_items.append("Analyze optimal calling hours to reduce voicemail rate")

    # No-answer rate
    if na_rate > 25:
        insights.append({"type": "warning", "text": f"High no-answer rate ({na_rate}%). Patients may not be picking up."})
        action_items.append("Review caller ID display and call timing strategy")

    # Rejection breakdown
    if rejected > 0:
        rej_subs = db.execute(f"""
            SELECT sub_category, COUNT(*) as cnt FROM calls
            WHERE outcome = 'Rejected appointment' AND {where}
            GROUP BY sub_category ORDER BY cnt DESC
        """, params).fetchall()
        for rs in rej_subs:
            pct = round(rs["cnt"] / rejected * 100, 1)
            if pct >= 20:
                insights.append({
                    "type": "info",
                    "text": f"Top rejection reason: {rs['sub_category']} ({rs['cnt']} calls, {pct}% of rejections)"
                })
        if any(r["sub_category"] == "Has own doctor/provider" for r in rej_subs):
            action_items.append("Review patient lists — some already have providers")
        if any(r["sub_category"] == "Suspicious of call/AI" for r in rej_subs):
            action_items.append("Consider improving call script trust-building language")

    # Callbacks
    if callback > 0:
        action_items.append(f"{callback} patients requested callbacks — ensure follow-up is scheduled")

    # Language barrier
    if lang_barrier > 0:
        insights.append({"type": "info", "text": f"{lang_barrier} calls had language barriers."})
        action_items.append("Consider adding multilingual agent support")

    # Day-over-day comparison
    if date and date != "all":
        prev = db.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'Accepted appointment' THEN 1 ELSE 0 END) as accepted
            FROM calls
            WHERE call_date = date(?, '-1 day')
            {"AND workflow_group = ?" if group and group != "All" else ""}
        """, [date] + ([group] if group and group != "All" else [])).fetchone()
        prev_total = prev["total"] or 0
        if prev_total > 0:
            prev_conv = round(prev["accepted"] / prev_total * 100, 1)
            change = round(conversion - prev_conv, 1)
            if abs(change) > 5:
                direction = "up" if change > 0 else "down"
                t = "success" if change > 0 else "warning"
                insights.append({"type": t, "text": f"Conversion {direction} {abs(change)}pp vs yesterday ({prev_conv}% → {conversion}%)"})

    db.close()
    return {"insights": insights, "action_items": action_items}


# Serve frontend
from fastapi.responses import FileResponse

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))
