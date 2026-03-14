# Camu Health — Call Analysis Dashboard: Claude Code Handoff

## What This Is

This folder contains everything Claude Code needs to build a production web app version of the Call Analysis Dashboard that Cowork has been generating as a static HTML file. The goal is to move from a daily-regenerated HTML file to a hosted web app with a database backend that the whole team can access via a URL.

## What Exists Today (Built in Cowork)

1. **Daily CSV ingestion** — The AI calling vendor drops a CSV each morning (`outgoing_calls_YYYY-MM-DD_HH-MM.csv`) containing patient calls with transcripts.
2. **Call classifier** (`classifier.py`) — A Python function that parses each call's transcript and assigns an outcome (Accepted appointment, Rejected appointment, Voicemail left, etc.) and a granular sub-category (Has own doctor, Feels fine, VM system detected, etc.) using a priority-based rules engine.
3. **Excel report generation** — Each day produces a `Call Analysis - YYYY-MM-DD.xlsx` with a Call Data sheet and a Workflow Analysis sheet.
4. **Interactive HTML dashboard** (`dashboard_design_reference.html`) — A self-contained HTML file with Chart.js that shows longitudinal trends, follow-up queues, time-of-day analysis, and script comparisons. This is the design reference for the web app.
5. **Slack summary** — A daily message posted to #daily-call-analysis with workflow-level metrics.

## What Needs to Be Built in Claude Code

A web application that replaces the static HTML dashboard with a proper hosted app. Specifically:

### Backend
- **CSV ingestion endpoint or watcher** — Automatically processes new CSVs when they appear, or accepts uploads via an API endpoint.
- **Database** — Store all classified call data (SQLite for simplicity or Postgres for production). Schema should cover: calls table (patient, EHR ID, phone numbers, timestamp, duration, workflow, outcome, sub-category, summary, raw transcript), and a daily_stats materialized view or table for fast dashboard queries.
- **Classifier integration** — The `classifier.py` file contains the complete classification logic. Port it into the backend as a module. The `classify()` function takes a row dict and returns (outcome, sub_category).
- **API endpoints** for the dashboard:
  - `GET /api/stats?group=<group>&date=<date|all>` — KPI aggregations
  - `GET /api/trends?group=<group>` — Daily trend data for charts
  - `GET /api/calls?group=<group>&date=<date>&search=<term>&page=<n>` — Paginated call details
  - `GET /api/followup?group=<group>` — Follow-up queue with staleness
  - `GET /api/tod?group=<group>` — Time-of-day analysis
  - `GET /api/scripts` — Script/template comparison
  - `GET /api/insights?group=<group>&date=<date|all>` — AI-generated action items

### Frontend
- Use the `dashboard_design_reference.html` as the design spec. It has:
  - Sidebar with workflow group selector and section visibility toggles
  - Universal date toggle bar that flows through ALL components (KPIs, charts, insights, follow-up queue, call table)
  - KPI cards with day-over-day deltas
  - Action Items & Insights panel (changes per workflow + date combination)
  - Follow-up Queue with staleness indicators (green=today, yellow=yesterday, red=2+ days) and priority ranking
  - Charts: conversion rate trend line, stacked volume bars, outcome donut, sub-category horizontal bar
  - Time-of-day heatmap with conversion by hour
  - Script/template effectiveness comparison tables with winner callouts
  - Searchable, paginated call detail table with outcome pills and AI summaries
- The frontend should fetch data from the API instead of having it embedded as JSON.
- React or plain JS — either works. The design reference uses vanilla JS + Chart.js.

### Workflow Groups
Workflows are grouped into logical categories for the sidebar:
- **AWV/DM General**: workflow name = "260310_AWV_DM_General"
- **Diabetes Templates**: workflow name starts with "Diabetes"
- **AWV Templates**: workflow name starts with "AWV - Template"
- **Appointment Reminders**: workflow name starts with "Appointment Reminder"
- **No-Show/Cancel Recall**: workflow name starts with "No-Show/Cancel"
- **Insurance Updates**: workflow name starts with "Insurance"
- **Other**: anything else

### Insights Generation
The insights are generated per workflow group + date combination. The logic evaluates:
- Conversion rate assessment (strong >30%, moderate 15-30%, low 5-15%, very low <5%)
- Voicemail rate alerts (>40%)
- No-answer rate alerts (>25%)
- Rejection sub-category breakdowns with specific action recommendations
- Callback opportunity counts
- Language barrier flagging
- Day-over-day conversion change alerts (>5pp swing)

## Key Data Details

### Raw CSV columns (A-K):
- A: Patient Name
- B: Patient EHR ID
- C: From Number
- D: To Number
- E: Date & Time (format: "March 12, 2026, 05:35 PM")
- F: Duration (format: "1m 23s" or "45s")
- G: Workflow Name
- H: Workflow Task Name
- I: Appointment Booked (Yes/No)
- J: In Voicemail (TRUE/FALSE) — UNRELIABLE, ~50% miss rate
- K: Transcript (JSON-formatted: {"agent":"text"} {"user":"text"} concatenated)

### Classification outcomes (in priority order):
1. Accepted appointment (sub: Booked via system flag, Scheduling language confirmed, Third party confirmed)
2. Voicemail left (sub: VM flag detected, VM system detected in transcript, VM Spanish, Automated screening, Personal answering machine, VM number recitation)
3. Rejected appointment (sub: Has own doctor, Not interested, Doesn't recognize clinic, Suspicious of AI, Feels fine, Mobility issues)
4. Requested callback (sub: Busy/at work, Requested explicitly, Patient unavailable, Third party unavailable, Wants live person)
5. Other - No answer/Hangup (sub: No answer, Minimal response, Mostly inaudible)
6. Other - Engaged/Inconclusive, Language barrier, Wrong number/Deceased, Patient relocated, Third party answered, Inconclusive

### Color scheme:
- Accepted: #C6EFCE (green)
- Rejected: #FFC7CE (red)
- Callback: #FFEB9C (yellow)
- Voicemail: #BDD7EE (blue)
- No answer: #D9D9D9 (gray)
- Language barrier: #E2EFDA (light green)
- Wrong number/Deceased: #F2DCDB (light red)
- Engaged: #FCE4D6 (orange)

## Files in This Folder

- `README.md` — This file
- `classifier.py` — The complete call classification engine. The `classify()` function is the entry point.
- `dashboard_design_reference.html` — The current working dashboard (open in browser to see the full design). Use this as the visual/functional spec.
- `sample_data/sample_raw_calls.csv` — 20 rows of real raw data showing the CSV format and transcript structure.
- `sample_data/features_structure.json` — The data structures for follow-up queue, time-of-day, and script comparison features.

## Future Features (Pass 2)

These were scoped but not yet built:
1. **Patient longitudinal tracking** — Cross-reference by EHR ID across days to show contact history per patient (called 3x, voicemail twice then rejected, etc.)
2. **Weekly/monthly trend views** — Rolling averages, week-over-week comparisons, calendar heatmaps for longer-term pattern recognition
