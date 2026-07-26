Product Requirements Document
Grade Change Intelligence (GCI) for Paper Making Processes
Field
Value
Document ID
PRD-GCI-001
Version
1.0
Status
Approved for Hackathon Build
Author
Solutions Architecture
Date
2026-07-26
Scope
Hackathon MVP (advisory-only intelligence layer over Honeywell QCS/MD-MPC)
Review cadence
End of each build phase (P0 → P3)



0. How to read this document
Requirement keywords follow RFC 2119: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY.

Every requirement has a unique, stable ID (FR-*, NFR-*, DR-*, UX-*, SEC-*).
Every requirement is independently testable. If a requirement cannot be turned into a pass/fail test, it is a goal, not a requirement, and lives in §2.
Where a numeric threshold is stated, it is normative. Where a value is configurable, the default is normative and the config key is named.
"The System" = the GCI intelligence layer being built. "The Controller" = the existing Honeywell QCS / MD Multivariable MPC. The System never becomes the Controller.


1. Problem Statement
1.1 Context
Honeywell QCS already performs automatic grade change for paper machines: target calculation, trajectory calculation, readiness checks, and coordinated ramping of stock flow, filler flow, dryer steam pressure, machine speed, and reel. This is a strong, proven control backbone and is not being replaced.

The gap is not control execution. The gap is foresight, adaptation, and explanation:

Grade changes remain high-loss events. During transitions the mill produces off-spec paper, broke, or cull while quality variables settle. Losses are measured in tonnes and minutes, per transition, per machine, several times a day.
Operators juggle too many interacting variables. Stock flow, filler flow, steam pressure, machine speed, basis weight, moisture, ash, caliper, recipe limits, actuator constraints, and machine disturbances all move and interact simultaneously.
Traditional automation executes but does not learn. The Controller computes a trajectory and follows it. It does not consult the 400 similar transitions that already happened on this machine, and it does not know that transition #217 blew through spec because a specific steam header was already saturated.
Experienced operator knowledge is scarce. Skill shortages mean newer operators need guidance that explains what is happening and why the recommended action is right — not just a number.
Site data is underused. QCS history, MIS reports, DCS historian trends, operator actions, alarm history, scanner diagnostics, and quality outcomes are stored but not converted into actionable real-time guidance.
1.2 Problem to be solved
Build an intelligent, advisory grade-change system that predicts deviation of process variables from system specification during a grade change, with Basis Weight as the primary variable, recommends corrective setpoints inside safe operating limits, shortens stabilization time, and explains every prediction and recommendation with a traceable source of inference — while remaining a read-only advisor to the existing QCS control loop.
1.3 Primary quality target (normative definition)
Off-spec event (Basis Weight): a Basis Weight measurement is off-spec at time t when

| BW_measured(t) − BW_setpoint(t) |  >  0.025 × BW_setpoint(t)

i.e. absolute deviation exceeds 2.5 % of the active setpoint. BW_setpoint(t) is the ramping target published by the Controller during a transition, not the final grade target, unless the recipe defines otherwise (see DR-07).

Sustained off-spec event: off-spec condition true for ≥ T_persist consecutive scans, default T_persist = 3 scans (config: spec.persist_scans). Single-scan excursions are logged but do not trigger a P1 alert, to suppress scanner-noise false positives.


2. Goals, Non-Goals, and Success Metrics
2.1 Goals (G)
ID
Goal
G-1
Predict, with usable lead time, that Basis Weight will breach the ±2.5 % band during a grade transition
G-2
Recommend setpoint adjustments that keep the process inside safe operating limits
G-3
Reduce time-to-steady-state (stabilization time) versus the baseline trajectory
G-4
Explain every prediction and recommendation in operator language, with a cited source of inference
G-5
Surface correlations — including ones not encoded in the existing control model — and quantify their impact
G-6
Capture operator accept/reject on every suggestion and use it to measure suggestion quality

2.2 Non-Goals (NG) — explicitly out of scope
ID
Non-Goal
Rationale
NG-1
The System MUST NOT write setpoints directly to DCS/QCS in the MVP
Safety, OT segregation, certification burden. Advisory only.
NG-2
Replacing or retuning the MD-MPC controller
Controller is the backbone; GCI is a layer above it
NG-3
Cross-Direction (CD) profile control / CD actuator recommendations
MD-only for MVP; CD is a P3+ extension
NG-4
Multi-machine fleet optimization or scheduling of grade sequences
Single-machine scope for MVP
NG-5
Closed-loop autonomous execution
Explicitly deferred until suggestion acceptance rate and safety record justify it (§13)
NG-6
Replacing the mill historian, MES, or QCS as a system of record
GCI reads; it does not own process data

2.3 Success metrics (measurable, MVP acceptance)
ID
Metric
Definition
MVP target
M-1
Off-spec recall
fraction of true sustained off-spec BW events predicted with ≥ L_min lead time
≥ 0.85
M-2
Precision
fraction of raised alerts that were followed by a true off-spec event within the horizon
≥ 0.70
M-3
Lead time L_min
median seconds between alert and first off-spec scan
≥ 60 s (≥ 2 scanner passes)
M-4
False-alarm rate
alerts per transition with no corresponding event
≤ 1.0
M-5
Stabilization time reduction
Δ in T_stab vs. baseline (§2.4), on replay/simulation
≥ 15 % median
M-6
Explanation coverage
% of suggestions carrying ≥ 1 tagged inference source
100 % (hard gate)
M-7
Recommendation safety
% of recommended setpoints inside recipe + actuator limits
100 % (hard gate)
M-8
Feedback capture
% of surfaced suggestions with a recorded accept/reject/expire outcome
100 %

2.4 Stabilization time — normative definition
T_stab = seconds from grade change start event (GC_START) until Basis Weight enters and remains within ±1.0 % of the final grade setpoint for a continuous window of T_hold seconds.

Defaults: stab.band_pct = 1.0, stab.hold_s = 120. If the band is never held before the next GC_START, the transition is recorded as T_stab = censored and excluded from median calculations but reported in the censoring rate.

Rationale for making this explicit: "reduce stabilization time" is unmeasurable without a fixed band and hold window. Two teams using different bands produce non-comparable numbers.


3. Users and Jobs to Be Done
Persona
Context
Job to be done
What the System owes them
Machine Operator (primary)
Control room, mid-transition, high cognitive load
"Is this grade change going to go bad, and what do I do in the next 60 seconds?"
One clear risk state, ≤ 3 ranked actions, plain-language why, one-tap accept/reject
Process / Quality Engineer
Post-shift, weekly review
"Which loops actually drive our transition losses, and which correlations are we not modelling?"
Correlation explorer, impact ranking, transition post-mortems, model performance
Production Manager
Weekly / monthly
"How much broke are we making on transitions and is it improving?"
Losses per transition, T_stab trend, acceptance-rate trend
Controls / Automation Engineer
Commissioning + maintenance
"Are the limits, tags, and model still valid?"
Tag mapping config, limit config, drift alerts, model registry, audit log
Data Scientist (build/ops)
Offline
"Is the model still fit for purpose?"
Replay harness, backtests, drift dashboards, retraining pipeline



4. Assumptions, Dependencies, Constraints
4.1 Assumptions (A) — each with a fallback
ID
Assumption
If false → fallback
A-1
Historical data for ≥ 50 labelled grade transitions is available
Fall back to the physics-informed simulator (§5.4) to bootstrap training; degrade M-1 target to 0.75 and label the model PROVISIONAL
A-2
Recipe/grade table exposes per-grade limits for BW, moisture, ash, caliper
Derive empirical limits as p1/p99 of historical steady-state per grade; tag source as INFERRED_FROM_HISTORY (never as RECIPE)
A-3
QCS publishes GC_START / GC_END events or an equivalent grade-ID tag
Detect transitions by change-point detection on the BW setpoint tag (§6.2)
A-4
Scanner scan period ≈ 20–45 s; sheet transport dead time is bounded and knowable
Estimate dead time by cross-correlation of stock-flow step vs. BW response per grade; store per-grade θ
A-5
Read access to historian/OPC UA is available with ≤ 5 s staleness
Operate in replay mode from CSV/Parquet with a virtual clock; the same code path serves both (DR-10)


Design rule: the System is built against a data contract (§5.1), not against a specific historian. Real data and synthetic data enter through the same adapter interface. This is the single most important architectural decision in this PRD, because it is what makes the build safe under dataset uncertainty.
4.2 Constraints (C)
ID
Constraint
C-1
Recommendations MUST respect recipe limits, actuator ranges, and ramp-rate limits. A recommendation violating any limit MUST be suppressed, not clipped silently (see FR-14).
C-2
Advisory only. No write path to OT. Physical or logical one-way data flow from the process network.
C-3
Must run on a single commodity node for the MVP (≤ 8 vCPU, ≤ 16 GB RAM, no GPU required at inference).
C-4
Inference must complete well inside one scanner period (see NFR-1).
C-5
Every displayed number must be traceable to a raw tag, a recipe entry, a model version, or a computed feature — no unattributed values.

4.3 Dependencies (D)
Historian/OPC UA read endpoint (or file export) · Grade/recipe table · Operator action log · Alarm history · Scanner diagnostics/validity flags · MIS production/broke records.


5. Data Requirements
5.1 Canonical data contract (DR)
All ingestion normalizes to these five entities. This contract is the integration boundary.

5.1.1 process_timeseries

Column
Type
Notes
ts
timestamp, UTC, tz-aware
primary time key
machine_id
string


tag
string
canonical tag name (see 5.2)
value
float
engineering units
unit
string
validated against tag registry
quality
enum {GOOD,UNCERTAIN,BAD,STALE}
OPC-UA-style quality


5.1.2 grade_events

ts_start, ts_end, machine_id, grade_from, grade_to, transition_id, trigger {AUTO,MANUAL}, outcome {SUCCESS,DEGRADED,FAILURE}

5.1.3 recipe_limits

grade_id, variable, setpoint, lo_spec, hi_spec, lo_alarm, hi_alarm, ramp_rate_max, source

5.1.4 operator_actions

ts, machine_id, operator_id (pseudonymised), tag, old_value, new_value, action_type, free_text

5.1.5 suggestion_feedback (written by the System — §9)

suggestion_id, ts_issued, ts_responded, transition_id, type, payload_json, sources_json, predicted_effect_json, response {ACCEPTED,REJECTED,EXPIRED,SUPERSEDED}, reject_reason, operator_id, realised_effect_json, model_version
5.2 Minimum viable tag set
Class
Tags
Primary quality (targets)
BW_meas, BW_sp, MOIST_meas, MOIST_sp, ASH_meas, CALIPER_meas
Manipulated (actionable)
STOCK_FLOW, STOCK_FLOW_SP, FILLER_FLOW, FILLER_FLOW_SP, STEAM_PRESS_G1..Gn, MACHINE_SPEED, MACHINE_SPEED_SP, REEL_SPEED
Context / disturbance
HEADBOX_CONS, HEADBOX_PRESS, WHITE_WATER_CONS, BROKE_RATIO, RETENTION_AID_FLOW, VACUUM_*, DRYER_HOOD_TEMP, DRYER_HOOD_HUMID, WIRE_AGE, FELT_AGE
Controller state
MPC_MODE, MPC_ACTIVE_CONSTRAINTS, GC_PHASE, GC_PROGRESS_PCT, TARGET_TRAJECTORY_*
Health / validity
SCANNER_VALID, SCANNER_STANDARDIZING, SHEET_BREAK, ALARM_*


DR-01 — The System MUST operate in degraded-but-useful mode when any context tag is missing; it MUST refuse to start a transition assessment when any primary quality or manipulated tag is missing, and MUST say which tag is missing.

DR-02 — Tag mapping MUST live in a single declarative config (config/tags.yaml) mapping site tag → canonical tag → unit → expected range. No tag name may be hard-coded in application logic.
5.3 Data quality gates
ID
Rule
DR-03
Reject/flag samples where quality != GOOD; forward-fill for at most 2 × scan_period, then mark the feature STALE and downgrade prediction confidence
DR-04
Clamp-and-flag physically impossible values (negative flow, BW ≤ 0, moisture outside 0–100 %)
DR-05
Deduplicate on (ts,machine_id,tag), keeping last write
DR-06
Resample all tags to a common 5 s grid; scanner variables carry age_since_scan_s as an explicit feature rather than being interpolated as if continuous
DR-07
The BW spec band is computed against the ramping setpoint during a transition; if the recipe defines a transition-specific band, the recipe wins
DR-08
Timezone: all internal timestamps UTC; display in mill-local time with explicit offset. DST transitions must not create duplicate or missing transition IDs
DR-09
Clock skew between historian sources > 2 s MUST raise a data-health warning; > 30 s MUST disable prediction
DR-10
Live and replay ingestion MUST share one adapter interface (SourceAdapter.stream(from_ts, to_ts) -> Iterator[Frame]) so the model code cannot tell the difference

5.4 Synthetic data generator (required for A-1 fallback and for tests)
DR-11 — The System MUST ship a physics-informed simulator producing labelled grade transitions with:

Mass balance: BW ≈ (stock_flow × consistency × retention) / (machine_speed × trim_width) with grade-dependent retention
First-order-plus-dead-time (FOPDT) response of BW to stock flow and speed, with per-grade θ (transport delay, default 25 s) and τ
Moisture ↔ steam ↔ speed coupling with drying-capacity saturation
Ash ↔ filler-flow coupling with retention dynamics
Injectable faults: steam header saturation, retention drop, sheet break, scanner standardization gap, consistency upset, stuck actuator
Deterministic seeding so every test is reproducible

Rationale: the simulator is not a demo prop. It is the only way to generate labelled failure transitions in volume, and failures are the minority class that drives M-1.


6. Functional Requirements
6.1 Ingestion & transition detection
ID
Requirement
Priority
FR-01
The System MUST ingest process timeseries, grade events, recipe limits, operator actions, and alarms via SourceAdapter, in both live and replay modes
P0
FR-02
The System MUST detect the start of a grade transition within 10 s, using GC_START when available, else change-point detection on BW_sp / grade ID
P0
FR-03
The System MUST assign each transition a stable transition_id and bind all predictions, suggestions, and feedback to it
P0
FR-04
The System MUST classify transition phase: PRE_CHECK → RAMP → SETTLE → STEADY, and expose the current phase
P1

6.2 Prediction engine
ID
Requirement
Priority
FR-05
The System MUST produce, at every 5 s cycle during a transition, a probability that Basis Weight will be sustained off-spec (per §1.3) within a forward horizon H. Default H = 180 s (config predict.horizon_s), with additional heads at 60 s and 300 s
P0
FR-06
The System MUST produce a point forecast trajectory BW_hat(t+1..t+H) with a prediction interval (P10/P50/P90)
P0
FR-07
The prediction MUST account for sheet transport dead time θ: the model is trained on dead-time-aligned features so it predicts what will arrive at the scanner, not what the scanner already saw
P0
FR-08
The System MUST map probability to a discrete risk state — OK (p < 0.30), WATCH (0.30 ≤ p < 0.60), AT_RISK (0.60 ≤ p < 0.85), CRITICAL (p ≥ 0.85) — with thresholds configurable and calibrated per §8.3
P0
FR-09
The System SHOULD extend the same prediction head to moisture, ash, and caliper once BW meets M-1
P2
FR-10
The System MUST emit a NO_PREDICTION state with a stated reason (missing tag, stale data, unknown grade pair, sheet break, scanner standardizing) rather than a low-confidence guess
P0

6.3 Recommendation engine
ID
Requirement
Priority
FR-11
When risk ≥ AT_RISK, the System MUST produce 1–3 ranked setpoint recommendations, each specifying: tag, current value, recommended value, ramp rate, expected effect on BW, expected effect on T_stab, confidence, and time window in which to act
P0
FR-12
Recommendations MUST be generated by constrained optimization over a short horizon: minimize predicted spec violation + stabilization time, subject to recipe limits, actuator ranges, ramp-rate limits, and MPC-declared active constraints
P0
FR-13
The System MUST simulate the recommended action through its forward model and display the counterfactual trajectory ("if you do nothing" vs. "if you accept")
P0
FR-14
Any recommendation whose value or ramp would violate a hard limit MUST be suppressed and replaced by an explicit message naming the binding constraint. Silent clipping is prohibited
P0
FR-15
The System MUST NOT issue recommendations that conflict with an active MPC constraint; where the MPC is already saturated on a handle, the System MUST say so and recommend on a different handle
P0
FR-16
Recommendations MUST be rate-limited: no more than one suggestion set per suggest.min_interval_s (default 60 s) per transition, and a superseded suggestion MUST be marked SUPERSEDED, not silently dropped
P1
FR-17
The System SHOULD recommend a revised ramp trajectory (not only a single setpoint) when the analysis attributes risk to ramp shape rather than ramp target
P2

6.4 Explainability & source-of-inference tagging
ID
Requirement
Priority
FR-18
Every prediction and every recommendation MUST carry a structured sources[] array. Each source has type ∈ {RECIPE, HISTORICAL_ANALOG, CORRELATION_MODEL, PHYSICS_MODEL, OPERATOR_PRECEDENT, ALARM_CONTEXT, SIMULATION, INFERRED_FROM_HISTORY}, plus reference (recipe row ID, transition IDs, feature name, rule ID), weight (0–1), and confidence
P0
FR-19
Every suggestion MUST render a plain-language rationale of ≤ 40 words naming the top contributing factors, e.g. "Steam group 3 is within 4 % of its high limit while speed is still ramping; in 12 of 14 similar 80→120 gsm transitions this produced a +3.1 % BW excursion 90 s later."
P0
FR-20
The System MUST expose per-feature attribution (SHAP or equivalent) for the top 5 contributors to the current risk score, in engineering units, not normalized scores
P1
FR-21
The System MUST show k nearest historical analog transitions with their outcomes and what the operator did, linked to transition_id
P1
FR-22
Rationale text MUST be generated from the structured sources[] object. Free-text generation not grounded in that object is prohibited
P0

6.5 Correlation discovery
ID
Requirement
Priority
FR-23
The System MUST compute lagged cross-correlations between every candidate tag and BW deviation over the transition window, scanning lags 0–300 s, and rank by strength
P0
FR-24
The System MUST distinguish known correlations (declared in config/known_relationships.yaml, i.e. those the control model already accounts for) from novel correlations, and flag novel ones explicitly
P0
FR-25
Novel correlation candidates MUST pass a statistical gate before display: FDR-corrected significance (Benjamini–Hochberg, q = 0.05), minimum effect size, minimum support (≥ 10 transitions), and stability across a temporal train/test split
P0
FR-26
The System MUST quantify impact: estimated contribution of each correlated variable to BW deviation and to T_stab, in engineering units (gsm, seconds)
P0
FR-27
The System MUST project future state: if a correlated parameter continues its current trend/trajectory, forecast the resulting BW deviation and time-to-limit-breach
P0
FR-28
The System MUST label correlations as CORRELATION unless a causal test is applied; where Granger causality or a controlled step in history supports it, it MAY be labelled LIKELY_CAUSAL with the evidence attached
P1
FR-29
The System MUST rank loops/parameters by impact on stabilization time, and for the top-ranked ones suggest setpoints that historically stabilized the system fastest
P0


Anti-requirement: the System MUST NOT present an unqualified correlation as an action driver. Spurious correlation on 400 tags is the default outcome of naive scanning; FR-25 exists specifically to prevent it.
6.6 Human-in-the-loop feedback
ID
Requirement
Priority
FR-30
Every suggestion surfaced to an operator MUST be individually acceptable or rejectable
P0
FR-31
Rejection MUST capture a reason from a fixed taxonomy (UNSAFE, WRONG_HANDLE, TOO_LATE, ALREADY_DOING_IT, DISAGREE_WITH_DIAGNOSIS, NOT_APPLICABLE_TO_THIS_GRADE, OTHER + free text)
P0
FR-32
Un-actioned suggestions MUST auto-expire after suggest.ttl_s (default 300 s) and be recorded as EXPIRED — never silently discarded
P0
FR-33
The System MUST persist every suggestion with its full inputs, model version, and outcome, immutably and append-only
P0
FR-34
The System MUST compute realised effect post-hoc: did BW go off-spec, and what was T_stab, for accepted vs. rejected vs. expired suggestions
P0
FR-35
The System MUST display suggestion quality analytics: acceptance rate, precision/recall over time, per suggestion type, per grade pair, per model version
P1
FR-36
Feedback SHOULD feed a retraining loop; retraining MUST NOT be automatic to production — it requires an explicit promote step (§8.5)
P2

6.7 Dashboard
ID
Requirement
Priority
UX-01
Live Transition view: current risk state, BW actual vs. setpoint vs. spec band vs. predicted trajectory with uncertainty band, countdown to predicted breach, active suggestions with accept/reject, phase indicator, data-health badge
P0
UX-02
Correlation Explorer: ranked correlations with lag, strength, effect size, novel/known badge, support count, and impact in gsm and seconds; drill-down to the scatter/lag plot and to the contributing transitions
P0
UX-03
Future State panel: for each correlated parameter trending out of range, projected trajectory and predicted BW impact if the trend continues, plus the recommended setpoint that avoids it
P0
UX-04
Stabilization Impact view: loops/parameters ranked by contribution to T_stab, with historically-fastest-stabilizing setpoint suggestions per grade pair
P0
UX-05
Suggestion Log / Feedback Quality view: full history with sources, responses, realised effects, and accuracy trend
P0
UX-06
Every displayed suggestion MUST show its source-of-inference chips inline (e.g. RECIPE, HISTORY ×14, PHYSICS) — not hidden behind a click
P0
UX-07
Colour MUST NOT be the sole carrier of risk state (WCAG 2.2 AA); state text and shape accompany colour. Control-room displays are frequently viewed at distance and by colour-vision-deficient operators
P1
UX-08
The dashboard MUST degrade visibly, not silently: a data-health banner names any stale/missing tag and the resulting capability loss
P0
UX-09
Operator-facing views MUST be readable at 3 m on a 1080p control-room display: minimum 16 px body text, high contrast, no dense tables in the live view
P2
UX-10
The live view MUST update within 2 s of a new prediction cycle and MUST NOT re-order suggestions while an operator is mid-interaction
P1



7. System Architecture
7.1 Module map
┌──────────────────────────────────────────────────────────────────────────┐

│                        OT / PROCESS NETWORK  (read-only)                  │

│   QCS/MD-MPC · DCS Historian · Scanner · Alarms · Recipe DB · MIS        │

└───────────────────────────────┬──────────────────────────────────────────┘

                                │  one-way / read-only  (SEC-01)

┌───────────────────────────────▼──────────────────────────────────────────┐

│ M1  INGESTION & ADAPTER LAYER                                            │

│     SourceAdapter (live OPC-UA / historian | replay Parquet | simulator) │

│     → validation (DR-03..09) → canonical contract (§5.1)                 │

└───────────────────────────────┬──────────────────────────────────────────┘

                                │ normalized frames @5 s

┌───────────────────────────────▼──────────────────────────────────────────┐

│ M2  FEATURE & CONTEXT ENGINE                                             │

│     transition detection · phase classification · dead-time alignment    │

│     rolling stats, rates, ratios · constraint proximity · analog lookup  │

│     → Feature Store (online: last N min | offline: full history)         │

└───────┬──────────────────────────────┬──────────────────────────┬────────┘

        │                              │                          │

┌───────▼─────────────┐  ┌─────────────▼────────────┐  ┌──────────▼───────┐

│ M3 PREDICTION       │  │ M4 CORRELATION DISCOVERY │  │ M5 KNOWLEDGE     │

│  risk classifier    │  │  lagged corr + FDR gate  │  │  recipe limits   │

│  BW trajectory fcst │  │  novel vs known          │  │  analog library  │

│  uncertainty (P10/  │  │  impact quantification   │  │  operator        │

│  P50/P90)           │  │  trend projection        │  │  precedents      │

└───────┬─────────────┘  └─────────────┬────────────┘  └──────────┬───────┘

        │                              │                          │

┌───────▼──────────────────────────────▼──────────────────────────▼────────┐

│ M6  RECOMMENDATION & SAFETY ENGINE                                       │

│     constrained optimization over forward model                          │

│     → SAFETY GATE: recipe limits, actuator ranges, ramp limits,          │

│       MPC active constraints  (FR-14 — suppress, never clip)             │

└───────────────────────────────┬──────────────────────────────────────────┘

                                │ candidate suggestions

┌───────────────────────────────▼──────────────────────────────────────────┐

│ M7  EXPLANATION & PROVENANCE ENGINE                                      │

│     assemble sources[] · SHAP attribution · analog citation              │

│     · template-grounded natural language (FR-22)                         │

└───────────────────────────────┬──────────────────────────────────────────┘

                                │ explained suggestions

┌───────────────────────────────▼──────────────────────────────────────────┐

│ M8  API LAYER (REST + WebSocket)                                         │

└───────┬──────────────────────────────────────────────┬───────────────────┘

        │                                              │

┌───────▼───────────────────────┐        ┌─────────────▼───────────────────┐

│ M9  DASHBOARD (UX-01..10)     │───────▶│ M10 FEEDBACK & AUDIT STORE      │

│     accept / reject           │        │     append-only suggestion log  │

└───────────────────────────────┘        │     realised-effect evaluator   │

                                         └─────────────┬───────────────────┘

                                                       │

                                         ┌─────────────▼───────────────────┐

                                         │ M11 MODEL REGISTRY & MONITORING │

                                         │  versions · drift · promote gate│

                                         └─────────────────────────────────┘
7.2 Inter-module contracts (all JSON, all versioned)
Edge
Payload
Contract note
M1→M2
Frame{ts, machine_id, tags:{name:{value,quality}}}
fixed 5 s cadence, gaps explicit
M2→M3/M4
FeatureVector{ts, transition_id, phase, features:{}, staleness:{}}
feature names are a versioned schema; unknown feature ⇒ reject, not ignore
M3→M6
RiskAssessment{p_offspec:{60,180,300}, trajectory:{p10,p50,p90}, state, attribution[]}


M4→M6/M9
CorrelationSet{items:[{tag, lag_s, strength, effect_size, novel:bool, support_n, q_value, impact_gsm, impact_t_stab_s, projection}]}


M5→M6
Constraints{recipe_limits, actuator_ranges, ramp_limits} + Analogs{transition_ids[], outcomes[]}


M6→M7
CandidateSuggestion{tag, from, to, ramp, predicted_effect, feasible:bool, binding_constraint?}
infeasible candidates pass through labelled, so the UI can explain suppression
M7→M8
Suggestion{id, ..., sources[], rationale_text, confidence}
sources[] non-empty is a hard invariant (M-6)
M9→M10
Feedback{suggestion_id, response, reason, operator_id, ts}


M10→M11
EvaluationRecord{...realised_effect...}



7.3 Technology (MVP, justified)
Layer
Choice
Why
Ingestion/replay
Python 3.12, Polars/Pandas, Parquet
one code path for live and replay; columnar replay is fast enough to iterate in a hackathon
Risk model
Gradient-boosted trees (LightGBM/XGBoost) on windowed features
best accuracy-per-hour on tabular industrial data; native SHAP; trains in seconds; interpretable — a deep net that cannot explain itself fails FR-18
Trajectory forecast
FOPDT/state-space grey-box + residual GBT
physics gives extrapolation safety outside the training envelope; ML corrects the residual
Uncertainty
Quantile regression (P10/P50/P90) + conformal calibration
calibrated intervals, no distributional assumption
Optimization
Bounded grid/CMA-ES over ≤ 3 handles on the forward model
small action space; deterministic; explainable; no solver dependency risk
Serving
FastAPI + WebSocket
streaming push to the live view
Store
SQLite (MVP) / TimescaleDB (prod path), Parquet for features
zero-ops for the hackathon, clear upgrade path
Dashboard
React + Plotly/Recharts
fast interactive time-series
Registry/audit
MLflow-compatible metadata + append-only event log
reproducibility, promote gate

7.4 Deployment topology
Single container-composed stack (ingest, engine, api, ui, db). Runs fully offline. Deployed on the IT/DMZ side of the OT boundary, reading from a historian replica or a one-way data diode. No inbound path to OT exists in the design — not "is blocked", does not exist.


8. Model Requirements
8.1 Labelling
NFR-M1 — Label y = 1 for a feature vector at time t if a sustained off-spec BW event (§1.3) begins in (t, t+H]. Labels MUST be generated by a single deterministic function shared by training and evaluation. Two label functions = two truths = an unfalsifiable model.
8.2 Validation protocol (non-negotiable)
NFR-M2 — Splits MUST be grouped by transition_id and ordered in time (train on older transitions, test on newer). Random row-level splits leak, because adjacent 5 s rows within a transition are near-identical, and would inflate M-1 to a meaningless number.

NFR-M3 — A naive baseline MUST be reported alongside every model result: (a) "always predict no event", (b) linear extrapolation of BW, (c) threshold-on-current-deviation. A model that does not beat (c) is not shipped.

NFR-M4 — Class imbalance MUST be handled by class weighting or focal loss, and the primary reported metric MUST be PR-AUC, not ROC-AUC or accuracy.
8.3 Calibration
NFR-M5 — Predicted probabilities MUST be calibrated (isotonic or Platt) on a held-out set; reliability curve and Brier score MUST be reported. Risk thresholds in FR-08 are only meaningful on calibrated probabilities.
8.4 Drift & degradation
NFR-M6 — The System MUST monitor input drift (PSI per feature), prediction drift, and rolling live precision/recall. Breaching drift.psi_threshold (default 0.25) on any top-10 feature MUST raise a maintenance alert and annotate the dashboard.

NFR-M7 — On an unseen grade pair with no historical analogs, the System MUST enter LOW_CONFIDENCE mode: physics-based prediction only, wider intervals, and suggestions marked "no historical precedent".
8.5 Model governance
NFR-M8 — Every model artifact MUST be versioned with: training data range, feature schema version, hyperparameters, metrics, and code commit. Every suggestion records the model_version that produced it.

NFR-M9 — Promotion to production requires an explicit gate: new model must beat incumbent on M-1/M-2 on the same held-out transitions, and must not regress M-7 (safety) at all.


9. Non-Functional Requirements
ID
Requirement
Target
NFR-1
End-to-end latency: new sample → updated risk on screen
P95 < 2 s, hard ceiling 5 s (must fit inside one scanner scan)
NFR-2
Prediction cycle cadence
every 5 s during a transition; every 30 s at steady state
NFR-3
Throughput
≥ 500 tags at 1 Hz on the MVP node without backpressure
NFR-4
Replay speed
≥ 100× real time, for iteration and backtesting
NFR-5
Availability
System failure MUST NOT affect the Controller — advisory path is strictly non-blocking
NFR-6
Graceful degradation
ordered fallback: full model → physics-only → limits-and-alarms-only → data-health banner. Never a blank screen, never a stale number without a staleness badge
NFR-7
Determinism
identical replay input + identical model version ⇒ byte-identical suggestions
NFR-8
Auditability
every suggestion reconstructable from the log alone: inputs, model version, sources, response, realised effect
NFR-9
Config over code
limits, thresholds, tags, horizons in versioned config; no magic numbers in source
NFR-10
Observability
structured JSON logs with transition_id correlation, health endpoint, metrics endpoint
NFR-11
Scalability path
horizontal scale by machine_id partition; stateless engine workers; state in the store
NFR-12
Portability
runs air-gapped; no external API calls at inference time
NFR-13
Test coverage
≥ 80 % on the safety gate and limit-checking modules specifically; every edge case in §11 has a named test
NFR-14
Reproducibility
pinned dependencies, seeded randomness, containerised build



10. Security, Safety & Compliance
ID
Requirement
SEC-01
No write path to OT. Read-only historian/OPC-UA credentials. Architecture aligned to IEC 62443 zone/conduit separation; GCI sits in a higher zone than the control system
SEC-02
Operator IDs MUST be pseudonymised in analytics; raw IDs only in the audit store, access-controlled
SEC-03
Role-based access: Operator (view + accept/reject), Engineer (+ config, correlations), Admin (+ model promotion). Model promotion MUST NOT be available to the Operator role
SEC-04
The audit log MUST be append-only and tamper-evident (hash chain over records)
SEC-05
Secrets via environment/secret store, never in config files or the repo
SEC-06
Every UI screen MUST carry a persistent "Advisory only — operator retains full control" affordance
SEC-07
Dependency scanning (SBOM) in CI; no known-critical CVEs at release
SAF-01
The safety gate (FR-14) MUST be a separate module with no ML dependency, so limit enforcement cannot be degraded by a model change
SAF-02
Recommendations MUST be suppressed entirely during SHEET_BREAK, SCANNER_STANDARDIZING, or MPC not in a normal mode — with the reason displayed
SAF-03
Automation-bias mitigation: confidence and evidence strength are displayed on every suggestion; low-support suggestions are visually distinguished from high-support ones



11. Edge Cases and Required Handling
Each row is a required, named test case (NFR-13).
11.1 Data
#
Edge case
Required behaviour
E-01
Scanner off-sheet / standardizing mid-transition
Suspend BW-measurement-based scoring, switch to physics-only estimate, badge as ESTIMATED, suppress suggestions (SAF-02)
E-02
Tag dropout / frozen value (same value N cycles)
Detect flatline, mark STALE, downgrade confidence, name the tag on the health banner
E-03
Historian backfill arrives late, out of order
Idempotent upsert; recompute affected transition post-hoc; never rewrite an already-issued suggestion — issue a correction record
E-04
Clock skew / DST / leap second
UTC internally; skew > 2 s warns, > 30 s disables prediction (DR-09)
E-05
Unit mismatch (gsm vs lb/3000ft², bar vs psi)
Unit declared in the tag registry and validated at ingest; mismatch is a startup failure, not a runtime surprise
E-06
Duplicate/overlapping grade events
Deterministic resolution rule (latest ts_start wins); overlap logged as a data-quality defect
E-07
Missing recipe entry for the target grade
NO_PREDICTION with reason UNKNOWN_GRADE; offer history-inferred limits explicitly tagged INFERRED_FROM_HISTORY

11.2 Process
#
Edge case
Required behaviour
E-08
Sheet break during transition
Abort transition scoring, mark transition_id outcome ABORTED, exclude from T_stab statistics, resume detection on restart
E-09
Operator aborts / reverses the grade change mid-ramp
Close the transition as REVERSED, open a new transition_id; do not attribute the reversal to model failure
E-10
Two grade changes back-to-back before steady state reached
T_stab censored; prediction continues with an explicit "chained transition" flag; analogs restricted to chained cases
E-11
Actuator saturated (steam header at limit, speed at max)
Recommend on an alternative handle; state the saturated handle by name (FR-15)
E-12
Manual mode / MPC off
Suppress trajectory-dependent suggestions; keep limits and correlation monitoring; display mode prominently
E-13
Grade pair never seen before
LOW_CONFIDENCE mode (NFR-M7); physics-only; suggestions tagged "no historical precedent"
E-14
Large disturbance unrelated to the transition (consistency upset, broke surge)
Attribution must separate transition-driven from disturbance-driven deviation; rationale must say which
E-15
Trim width / reel change concurrent with grade change
Include as a feature; if unmodelled, widen intervals and flag confounded transition
E-16
Recipe changed by an engineer mid-transition
Re-read limits; if the spec band moves, recompute risk and mark prior suggestions SUPERSEDED

11.3 Model & recommendation
#
Edge case
Required behaviour
E-17
Model predicts a breach that never occurs (false positive)
Recorded against M-2; post-hoc evaluator distinguishes "false alarm" from "operator acted and prevented it" using the feedback record — this distinction is required, or M-2 is meaningless
E-18
Operator accepts a suggestion but does not execute it
Detect divergence between accepted setpoint and observed tag; record ACCEPTED_NOT_EXECUTED; exclude from realised-effect attribution
E-19
Two suggestions with conflicting directions
Conflict detector; only the higher-ranked one is surfaced; the conflict is logged
E-20
Correlation is real but spurious (confounded by grade sequence)
FDR gate + support minimum + temporal stability check (FR-25); confounder list checked before promotion to the "novel" panel
E-21
Model confidence high but data staleness high
Confidence is multiplicatively penalised by staleness; a stale-input high-confidence suggestion must not be displayable
E-22
Suggestion arrives too late to be actionable
If remaining lead time < action dead time for that handle, mark TOO_LATE_TO_ACT and show a mitigation instead of a prevention

11.4 System & UX
#
Edge case
Required behaviour
E-23
Engine crash mid-transition
Restart recovers transition_id from the store, resumes, and clearly marks the coverage gap
E-24
Dashboard disconnects (WebSocket drop)
Visible "disconnected — data is N s old" banner; auto-reconnect and backfill; never render stale data as live
E-25
Multiple operators respond to the same suggestion
First response wins; second sees "already actioned by "; both recorded
E-26
Alert fatigue
Rate limiting (FR-16), risk-state hysteresis (must clear a lower band for 2 cycles before downgrading), and de-duplication of repeated identical suggestions
E-27
Very long transition (> 1 h)
Rolling window features bounded; memory bounded; no unbounded accumulation
E-28
Empty/cold start (no history at all)
Physics-only mode, simulator-trained provisional model, banner stating the System is unvalidated on this machine



12. Acceptance Criteria (Definition of Done)
The MVP is complete when all of the following hold on the held-out evaluation set (real data if available, else simulator-generated with injected faults):

#
Criterion
Gate
AC-1
BW off-spec prediction achieves recall ≥ 0.85, precision ≥ 0.70, median lead time ≥ 60 s, on transition-grouped, time-ordered holdout
Hard
AC-2
Model beats all three naive baselines (NFR-M3) on PR-AUC
Hard
AC-3
100 % of issued recommendations lie within recipe + actuator + ramp limits; a deliberate limit-violating candidate is provably suppressed with the binding constraint named
Hard
AC-4
100 % of suggestions carry a non-empty sources[] and a ≤ 40-word grounded rationale
Hard
AC-5
Correlation panel distinguishes known vs novel, and every novel item passes the FDR + support + stability gate
Hard
AC-6
Future-state projection renders for every correlated parameter trending out of range, with predicted BW impact and time-to-breach
Hard
AC-7
Stabilization-impact ranking renders, and applying its top suggestion in replay reduces median T_stab by ≥ 15 %
Hard
AC-8
Accept/reject is available on every suggestion; all responses (incl. EXPIRED) persist with realised-effect evaluation
Hard
AC-9
Suggestion-quality analytics view renders acceptance rate and rolling precision/recall by model version
Hard
AC-10
Architecture document with the module map and every inter-module contract from §7.2
Hard
AC-11
Every edge case in §11 has a passing named test
Hard
AC-12
Full replay of a held-out transition runs end-to-end from a single command and reproduces byte-identical suggestions on a second run
Hard
AC-13
System degrades correctly when a primary tag is removed at runtime (demonstrated live)
Hard



13. Phasing
Phase
Deliverable
Exit criterion
P0 — Foundation
Data contract, adapters (replay + simulator), transition detection, limits/safety gate, storage schema
A labelled transition replays end-to-end; safety gate rejects an out-of-limit action
P1 — Intelligence
Feature engine with dead-time alignment, risk classifier, trajectory forecast + intervals, calibration, baselines
AC-1, AC-2 met
P2 — Guidance
Recommendation optimizer, counterfactual simulation, explanation/provenance engine, analog library
AC-3, AC-4 met
P3 — Surface
Correlation discovery + FDR gate, dashboard (UX-01..05), feedback loop, quality analytics
AC-5..AC-9 met
Post-MVP
Moisture/ash/caliper heads, CD extension, MPC constraint co-optimization, supervised closed-loop pilot
Requires ≥ 6 months of acceptance-rate evidence and a formal HAZOP before any write path is considered



14. Risks and Mitigations
Risk
Likelihood
Impact
Mitigation
Insufficient labelled failure transitions
High
High
Simulator (DR-11) with injected faults; class weighting; provisional model labelling
Spurious correlations dominate the novel panel
High
Medium
FDR correction, support minimum, temporal stability, known-relationship exclusion list
Data leakage inflates offline metrics
Medium
High
Transition-grouped, time-ordered splits (NFR-M2); baselines always reported
Alert fatigue kills adoption
Medium
High
Precision target ≥ 0.70, rate limiting, hysteresis, dedup (E-26)
Automation bias — operator over-trusts a wrong suggestion
Medium
High
Confidence + evidence strength always visible; low-support suggestions visually distinct (SAF-03)
Tag naming differs per site
High
Medium
Declarative tag mapping (DR-02); zero hard-coded tags
Dead time mis-estimated ⇒ predictions systematically early/late
Medium
High
Per-grade θ estimated by cross-correlation (A-4); residual monitoring
Scope creep into closed-loop control
Medium
High
NG-1/NG-5 are contractual; safety gate is a separate non-ML module



15. Open Questions
#
Question
Owner
Needed by
Default if unanswered
OQ-1
Is GC_START/GC_END published as an event, or must transitions be inferred?
Controls
P0
Infer via change-point on BW_sp (A-3)
OQ-2
Does the recipe define transition-specific spec bands, or only steady-state?
Quality
P0
Use steady-state band against the ramping setpoint (DR-07)
OQ-3
Scanner scan period and whether MD estimates are exposed separately from scan averages
Controls
P1
Assume 30 s scan, treat scan average as the measurement, carry age_since_scan_s
OQ-4
Are MPC active constraints readable as tags?
Controls
P2
Infer saturation from actuator proximity to limit
OQ-5
Cost per tonne of broke, for loss quantification
Production
P3
Report tonnes and minutes only, not currency



Appendix A — Glossary
BW Basis Weight (gsm) · MD Machine Direction · CD Cross Direction · MPC Model Predictive Control · QCS Quality Control System · DCS Distributed Control System · Broke off-spec paper recycled back into the process · Cull rejected product · Grade change coordinated transition between product recipes · θ transport dead time from wet end to scanner · T_stab stabilization time (§2.4) · FOPDT First Order Plus Dead Time · FDR False Discovery Rate · PSI Population Stability Index · PR-AUC Precision–Recall Area Under Curve.
Appendix B — Configuration keys (normative defaults)
spec:

  bw_band_pct: 2.5

  persist_scans: 3

stab:

  band_pct: 1.0

  hold_s: 120

predict:

  horizon_s: 180

  extra_horizons_s: [60, 300]

  cycle_s: 5

risk_thresholds: {watch: 0.30, at_risk: 0.60, critical: 0.85}

suggest:

  min_interval_s: 60

  ttl_s: 300

  max_per_set: 3

correlation:

  max_lag_s: 300

  fdr_q: 0.05

  min_support_transitions: 10

drift:

  psi_threshold: 0.25

data:

  resample_s: 5

  max_forward_fill_scans: 2

  clock_skew_warn_s: 2

  clock_skew_disable_s: 30

