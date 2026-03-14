# Prompt for Claude Code

Copy and paste this into Claude Code after navigating to your project folder.

---

## The Prompt

I'm building a web app for Camu Health's call center analytics. Read the README.md in this folder first — it has the full context, data schema, classification logic, and feature specs.

Here's what I need:

**Backend (Python + FastAPI + SQLite):**
1. A CSV ingestion module that reads our vendor's raw call CSVs, classifies each call using the logic in `classifier.py`, generates an AI summary of each transcript, and stores everything in a SQLite database.
2. API endpoints for: aggregated stats (filterable by workflow group + date), daily trend data, paginated call details with search, follow-up queue with staleness tracking, time-of-day analysis, script/template comparison, and AI-generated action items/insights.
3. The classifier in `classifier.py` is battle-tested — port it as-is into a module, don't rewrite the rules.

**Frontend (React + Chart.js or Recharts):**
1. Open `dashboard_design_reference.html` in a browser — that's the exact design I want. Match the layout, color scheme, and interaction patterns.
2. Key interaction: a universal date toggle bar at the top. When you click a specific day, EVERY component updates — KPIs, charts, insights, follow-up queue, call table. "All Days" shows the aggregate.
3. Sidebar with workflow group selector (AWV/DM General, Diabetes Templates, Appointment Reminders, etc.) and section visibility toggles.
4. Six sections: Action Items & Insights, Follow-Up Queue (with green/yellow/red staleness dots), Charts (conversion trend, volume bars, outcome donut, sub-category bar), Time-of-Day heatmap, Script Comparison tables, and searchable Call Details table.

**Data:**
- Look at `sample_data/sample_raw_calls.csv` for the CSV format.
- Look at `sample_data/features_structure.json` for the follow-up queue, time-of-day, and script comparison data structures.
- The transcript format is concatenated JSON objects like `{"agent":"text"} {"user":"text"}`.

Start by reading all the files in this folder, then scaffold the project and build it out. Make sure the app runs locally with `uvicorn` or similar, and give me instructions to start it up.
