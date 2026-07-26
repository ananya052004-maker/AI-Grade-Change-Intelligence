# Grade Change Intelligence — Hackathon Submission

**Challenge**: Predict Basis Weight off-spec risk during paper-machine grade changes,
recommend setpoints, reduce stabilization time, and explain every suggestion —
built as an intelligence layer on top of Honeywell's existing QCS grade-change control.

This repo now targets **PRD-GCI-001** (`docs/prd.md/prd_grade_change.md`), a much more
rigorous spec than the original screenshot brief. The primary deliverable is
`backend/` + `frontend/`; see **`docs/TRACEABILITY_MATRIX.md`** for exactly which
requirement IDs are met, partial, or deferred. The original Streamlit build (`src/`)
still works and is kept as a lightweight legacy view.

## Quick Start — primary build (FastAPI + React, PRD-compliant)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload        # trains models on startup, serves http://localhost:8000
```
```bash
cd frontend
npm install
npm run dev                          # dashboard at http://localhost:5173
```
Run the test suite: `cd backend && pytest tests/ -v`
Or via Docker: `docker compose up --build` (backend on :8000, frontend on :8080).

## Quick Start — legacy Streamlit view
```bash
pip install -r requirements.txt
python3 src/data_simulator.py      # generates 140 synthetic historical grade-change events
streamlit run src/app.py           # launches the dashboard at http://localhost:8501
```

## Project Structure
```
grade_change_intel/
├── src/
│   ├── data_simulator.py       # generates realistic historical process data
│   ├── intelligence_engine.py  # correlation discovery, risk model, recommender
│   └── app.py                  # Streamlit dashboard (main deliverable)
├── data/                       # generated CSVs + feedback.db (created on run)
├── docs/
│   └── SOLUTION_DOCUMENTATION.md   # architecture, module communication, rationale
└── requirements.txt
```

## What Each Hackathon Requirement Maps To
| Requirement | Where it's implemented |
|---|---|
| Predict off-spec risk | `intelligence_engine.py :: predict_risk()` (XGBoost + SHAP) |
| Recommend setpoints | `intelligence_engine.py :: recommend_setpoints()` (case-based retrieval) |
| Reduce stabilization time | Recommendation includes expected stabilization time from similar successful events |
| Rationale for prediction/recommendation | SHAP top-3 contributors shown in dashboard; every recommendation states its historical basis |
| New correlations not in current system | `discover_correlations()` — flags context vars (ambient humidity, operator skill) not in the known QCS loop list |
| Loops causing high stabilization impact | `stabilization_impact_ranking()` |
| Tag source of inference | Every dict returned by the engine includes a `source` field, shown in the UI |
| Accept/Reject + logging | Dashboard buttons write to `data/feedback.db` (SQLite), tracked live in the "Suggestion Quality Tracker" panel |

See `docs/SOLUTION_DOCUMENTATION.md` for full architecture diagram and design rationale
(section 0 explains how the legacy and primary builds relate), and
`docs/TRACEABILITY_MATRIX.md` for the PRD requirement-by-requirement status of the
primary `backend/`+`frontend/` build.
