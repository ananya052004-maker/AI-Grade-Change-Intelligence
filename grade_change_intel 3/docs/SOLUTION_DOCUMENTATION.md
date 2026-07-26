# Grade Change Intelligence — Solution Documentation

## 0. Two builds in this repo

This repo contains two things, built in sequence within the same working session:

1. **`src/` (legacy)** — a single-file Streamlit prototype built first, against the
   screenshot hackathon brief only. Still runs (`streamlit run src/app.py`), kept as a
   quick-look reference. The rest of this document (sections 1-7 below) describes it.
2. **`backend/` + `frontend/` (primary, PRD-compliant)** — built second, against the full
   `docs/prd.md/prd_grade_change.md` (PRD-GCI-001). This is a FastAPI + WebSocket + SQLite/
   Parquet backend and a React + Recharts frontend, implementing the PRD's own §7.1 module
   map (M1 ingestion/adapters, M2 features, M3 prediction, M4 correlation, M5 knowledge,
   M6 recommendation+safety, M7 explanation, M8 API, M9 dashboard, M10 feedback/audit, M11
   model registry) and §7.2 inter-module contracts as literal pydantic types in
   `backend/app/contracts.py`. Run with:
   ```bash
   cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
   cd frontend && npm install && npm run dev
   ```
   **`docs/TRACEABILITY_MATRIX.md` is the authoritative status document** for this build —
   every PRD requirement ID (FR/NFR/DR/UX/SEC/SAF/AC) mapped to Met/Partial/Deferred with
   a file reference, generated from the actual final code state rather than written
   speculatively. Read it before assuming any specific requirement is fully closed.

## 1. Problem Recap
Honeywell QCS executes grade changes (coordinated ramping of stock flow, filler flow,
steam pressure, machine speed) but does not *learn* from history. During transitions,
Basis Weight can deviate off-spec while quality variables stabilize, causing broke/cull
material. This solution adds an **intelligence layer on top of** (not a replacement for)
the existing QCS control loop.

## 2. Architecture / Building Blocks

```
┌─────────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                         │
│  historian_timeseries.csv | operator_actions.csv | alarm_history.csv│
│  (stand-in for real QCS history / MIS / DCS historian / scanner)    │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  INTELLIGENCE ENGINE  (src/intelligence_engine.py)                   │
│                                                                     │
│  ┌───────────────────┐  ┌────────────────────┐  ┌────────────────┐ │
│  │ Correlation        │  │ Risk Prediction     │  │ Setpoint       │ │
│  │ Discovery Module   │  │ Module              │  │ Recommendation │ │
│  │                    │  │                     │  │ Module         │ │
│  │ Pearson correlation│  │ XGBoost classifier  │  │ Case-based     │ │
│  │ of ALL variables   │  │ predicts P(off-spec │  │ retrieval of   │ │
│  │ (known loops +     │  │ within next 2 min)  │  │ similar         │ │
│  │ context vars) vs   │  │                     │  │ SUCCESSFUL     │ │
│  │ |BW deviation|      │  │ SHAP explainer      │  │ historical      │ │
│  │                    │  │ attributes each     │  │ transitions -   │ │
│  │ Flags correlations │  │ prediction to       │  │ recommends the  │ │
│  │ NOT in the known   │  │ specific features   │  │ setpoints THEY  │ │
│  │ loop list          │  │ ("rationale")       │  │ used at this    │ │
│  │                    │  │                     │  │ stage           │ │
│  └───────────────────┘  └────────────────────┘  └────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Stabilization Impact Ranking Module                           │ │
│  │ Correlates each loop's ramp aggressiveness (std of rate-of-   │ │
│  │ change) against historical stabilization_time_sec              │ │
│  └───────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬───────────────────────────────────┘
                                 │  (all outputs carry a `source` tag)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DASHBOARD  (src/app.py — Streamlit)                                 │
│  • Live/replay trend chart with projected trajectory                │
│  • Off-spec risk % + SHAP rationale                                 │
│  • Recommended setpoints table + expected stabilization time        │
│  • New-correlation table (highlighted)                              │
│  • Stabilization impact ranking table                               │
│  • Accept / Reject buttons on every suggestion                      │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FEEDBACK STORE  (SQLite: data/feedback.db)                          │
│  Logs every suggestion + operator Accept/Reject response,           │
│  enabling future evaluation of suggestion quality/accuracy over time│
└─────────────────────────────────────────────────────────────────────┘
```

## 3. Module Communication
1. **Data Layer → Intelligence Engine**: engine loads CSVs on startup (`GradeChangeIntelligence.__init__`), builds a shared feature table (`build_features`) used by every downstream module — a single source of truth so all modules see identical engineered features (current value + rate-of-change per variable).
2. **Intelligence Engine → Dashboard**: dashboard calls engine methods directly (in-process, no network hop needed for this prototype — a production version would expose these as REST/gRPC endpoints so the engine can run as an independent microservice next to the QCS historian).
3. **Dashboard → Feedback Store**: every Accept/Reject button click writes a row to SQLite via `log_feedback()`, capturing: timestamp, event, suggestion type, suggestion detail (JSON), source tag, and the operator's response.
4. **Feedback Store → Dashboard**: the "Suggestion Quality Tracker" panel reads back from SQLite to show acceptance rate — this is the loop that lets the *intelligence layer's own performance* be evaluated over time, directly per the brief's requirement.

## 4. Why This Design (Key Decisions & Rationale)
- **XGBoost + SHAP over a deep neural network**: the brief explicitly requires "rationale behind the prediction/recommendation" and "tag every suggestion with source of inference." SHAP gives exact, per-prediction feature attribution for a tree model essentially for free, and is far easier to defend live to judges/operators than a black-box network.
- **Case-based retrieval for setpoint recommendations (not pure optimization)**: recommending "here's what worked in N similar past transitions" is transparent, operator-trustable, and directly satisfies the brief's constraint to "use historical trends and trajectories during failures and success scenarios."
- **Correlation discovery separates "known loop" vs "not in system" variables**: directly satisfies "find new correlations not defined in the system but may have impacted the process" — `ambient_humidity` and `operator_skill` are modeled as real (simulated) drivers of stabilization delay that the current QCS loop list doesn't account for.
- **Every module output includes an explicit `source` field**: satisfies "tag every suggestion with possible source of inference."
- **SQLite feedback log**: lightweight, zero-setup, satisfies "solution should allow user to accept or reject a suggestion; responses must be recorded."

## 5. Data Note
`src/data_simulator.py` generates realistic synthetic grade-change data (140 events,
16,800 timestamped samples across 4 grades) because no dataset was provided in the
problem statement screenshots. **If Honeywell supplies a real historian export**,
point `DATA_DIR` in `intelligence_engine.py` at it — the schema expected is documented
in the CSV headers the simulator produces (event_id, t_sec, from_grade, to_grade, the
4 loop variables, basis_weight/moisture/ash/caliper, target_basis_weight).

## 6. How to Run
```bash
pip install pandas numpy xgboost shap streamlit plotly scipy
python3 src/data_simulator.py      # generates data/*.csv
streamlit run src/app.py           # launches dashboard
```

## 7. Future Scope (if more time were available)
- Replace linear trend projection with the trained XGBoost model itself for the
  "future state" chart line (currently a simple polyfit for demo speed).
- Move engine to a REST microservice so it can run against a live OPC-UA/historian feed.
- Add a proper optimizer (constrained on recipe/actuator limits) alongside the
  case-based recommender, and let the dashboard show both with their own source tags.
- Use the feedback log to retrain/re-weight the model (active learning loop).
