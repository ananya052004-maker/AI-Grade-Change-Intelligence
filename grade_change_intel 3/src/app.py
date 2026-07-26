"""
app.py — Grade Change Intelligence Dashboard
Run with: streamlit run src/app.py

Implements all dashboard deliverables from the hackathon brief:
- Show new correlations found + impact on the system
- Show current trend/trajectory + predicted future state if it continues
- Suggested setpoints to keep system in operational limits
- Loops/parameters causing high impact on stabilization + setpoints to stabilize faster
- Every suggestion tagged with source of inference
- Accept/Reject buttons, responses logged for evaluating suggestion quality
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import sqlite3
import datetime
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

from intelligence_engine import GradeChangeIntelligence, LOOP_COLS

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ---------------------------------------------------------------- setup
@st.cache_resource
def load_engine():
    gci = GradeChangeIntelligence()
    gci.train_risk_model()
    return gci


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_id TEXT,
            t_sec INTEGER,
            suggestion_type TEXT,
            suggestion_detail TEXT,
            source TEXT,
            user_response TEXT
        )
    """)
    conn.commit()
    return conn


def log_feedback(conn, event_id, t_sec, suggestion_type, detail, source, response):
    conn.execute(
        "INSERT INTO feedback_log (timestamp, event_id, t_sec, suggestion_type, suggestion_detail, source, user_response) VALUES (?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), event_id, t_sec, suggestion_type, str(detail), source, response),
    )
    conn.commit()


# ---------------------------------------------------------------- page
st.set_page_config(page_title="Grade Change Intelligence", layout="wide")
st.title("Grade Change Intelligence — Paper Making Process")
st.caption("Predicts Basis Weight risk, recommends setpoints, and explains why — built on top of Honeywell QCS grade-change control.")

gci = load_engine()
conn = init_db()

events = gci.events
event_options = events.sort_values("event_id").apply(
    lambda r: f"{r.event_id} | {r.from_grade}→{r.to_grade} | {r.event_outcome}", axis=1
).tolist()

col_sel1, col_sel2 = st.columns([2, 1])
with col_sel1:
    selected = st.selectbox("Select a grade-change event to inspect / replay", event_options, index=3)
    sel_event_id = selected.split(" | ")[0]
with col_sel2:
    max_t = int(gci.ts[gci.ts.event_id == sel_event_id].t_sec.max())
    t_cursor = st.slider("Replay position (seconds into event)", 0, max_t, min(600, max_t), step=15)

ev_row = events[events.event_id == sel_event_id].iloc[0]
ts_full = gci.ts[gci.ts.event_id == sel_event_id].sort_values("t_sec")
ts_so_far = ts_full[ts_full.t_sec <= t_cursor]
current_raw = ts_full[ts_full.t_sec == t_cursor].iloc[0]

feat_df = gci.build_features(gci.ts)
current_feats = feat_df[(feat_df.event_id == sel_event_id) & (feat_df.t_sec == t_cursor)].iloc[0]
current_row = current_feats[gci.feature_cols].to_dict()
current_row["t_sec"] = t_cursor

st.divider()

# ---------------------------------------------------------------- Row 1: trend + risk
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Basis Weight — Trend & Projected Trajectory")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts_so_far.t_sec, y=ts_so_far.basis_weight, mode="lines", name="Actual Basis Weight", line=dict(color="royalblue")))
    target = ev_row_target = ts_full.target_basis_weight.iloc[0]
    fig.add_hline(y=target, line_dash="dash", line_color="green", annotation_text="Target")
    fig.add_hline(y=target * 1.025, line_dash="dot", line_color="red", annotation_text="+2.5% limit")
    fig.add_hline(y=target * 0.975, line_dash="dot", line_color="red", annotation_text="-2.5% limit")
    # naive linear projection of the trend for the next 2 minutes (illustrates "future state if trend continues")
    if len(ts_so_far) >= 5:
        recent = ts_so_far.tail(8)
        slope = np.polyfit(recent.t_sec, recent.basis_weight, 1)[0]
        future_t = np.arange(t_cursor, t_cursor + 150, 15)
        future_bw = current_raw.basis_weight + slope * (future_t - t_cursor)
        fig.add_trace(go.Scatter(x=future_t, y=future_bw, mode="lines", name="Projected (if trend continues)", line=dict(color="orange", dash="dash")))
    fig.update_layout(height=380, xaxis_title="Time (s)", yaxis_title="Basis Weight")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Off-Spec Risk")
    risk = gci.predict_risk(current_row)
    p = risk["risk_probability"]
    color = "red" if p > 0.6 else ("orange" if p > 0.3 else "green")
    st.markdown(f"<h1 style='color:{color}'>{p*100:.1f}%</h1>", unsafe_allow_html=True)
    st.caption("Probability of exceeding ±2.5% Basis Weight deviation within the next 2 minutes")

    st.markdown("**Why (top SHAP contributors):**")
    for c in risk["top_contributors"]:
        st.write(f"- `{c['feature']}` — {c['direction']} (impact: {c['shap_contribution']:+.3f})")
    st.caption("Source: model_shap_explanation")

    if st.button("✅ Accept this risk assessment", key="acc_risk"):
        log_feedback(conn, sel_event_id, t_cursor, "risk_assessment", risk, "model_shap_explanation", "ACCEPTED")
        st.success("Logged.")
    if st.button("❌ Reject this risk assessment", key="rej_risk"):
        log_feedback(conn, sel_event_id, t_cursor, "risk_assessment", risk, "model_shap_explanation", "REJECTED")
        st.warning("Logged.")

st.divider()

# ---------------------------------------------------------------- Row 2: recommendation
st.subheader("Recommended Setpoints")
rec = gci.recommend_setpoints(ev_row.from_grade, ev_row.to_grade, current_row)

rcol1, rcol2 = st.columns([2, 1])
with rcol1:
    if rec.get("recommended_setpoints"):
        rec_df = pd.DataFrame([
            {"Loop": k, "Current": round(current_row.get(k, np.nan), 2), "Recommended": v,
             "Delta": round(v - current_row.get(k, 0), 2)}
            for k, v in rec["recommended_setpoints"].items()
        ])
        st.dataframe(rec_df, use_container_width=True, hide_index=True)
        st.caption(f"Based on {rec['based_on_n_events']} similar historical SUCCESS transitions. "
                    f"Expected stabilization time if followed: **{rec['expected_stabilization_time_sec']}s** "
                    f"(current event's actual: {ev_row.stabilization_time_sec if pd.notna(ev_row.stabilization_time_sec) else 'did not stabilize in window'}s)")
        st.markdown(f"**Source:** `{rec['source']}`")
    else:
        st.info("Not enough similar historical events to generate a recommendation yet.")

with rcol2:
    if st.button("✅ Accept setpoint recommendation", key="acc_rec"):
        log_feedback(conn, sel_event_id, t_cursor, "setpoint_recommendation", rec, rec.get("source", "unknown"), "ACCEPTED")
        st.success("Logged.")
    if st.button("❌ Reject setpoint recommendation", key="rej_rec"):
        log_feedback(conn, sel_event_id, t_cursor, "setpoint_recommendation", rec, rec.get("source", "unknown"), "REJECTED")
        st.warning("Logged.")

st.divider()

# ---------------------------------------------------------------- Row 3: correlations + stabilization impact
c3, c4 = st.columns(2)
with c3:
    st.subheader("Correlation Discovery (incl. new/undefined correlations)")
    corr_df = gci.discover_correlations()
    def highlight_new(row):
        return ['background-color: #fff3cd' if row.flag else '' for _ in row]
    st.dataframe(corr_df.style.apply(highlight_new, axis=1), use_container_width=True, hide_index=True)
    st.caption("Rows highlighted are correlations NOT part of the current QCS loop definition — "
               "candidates for new control logic or operator SOPs.")

with c4:
    st.subheader("Stabilization Impact Ranking")
    impact_df = gci.stabilization_impact_ranking()
    st.dataframe(impact_df, use_container_width=True, hide_index=True)
    st.caption("Variables whose ramp aggressiveness most correlates with slower/faster stabilization time.")

st.divider()

# ---------------------------------------------------------------- Row 3b: underused site data
st.subheader("Site Data for This Event — Operator Actions & Alarms")
st.caption("Per the brief: QCS history, operator actions, and alarm history are often stored but underused. "
           "Surfaced here as context/rationale, not yet fed into the models.")
c5, c6 = st.columns(2)
with c5:
    actions_df = gci.get_event_operator_actions(sel_event_id)
    st.markdown("**Operator Actions**")
    if not actions_df.empty:
        st.dataframe(actions_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No manual operator actions logged for this event.")
    st.caption("Source: `historian_data:operator_actions_log`")
with c6:
    alarms_df = gci.get_event_alarms(sel_event_id)
    st.markdown("**Alarms**")
    if not alarms_df.empty:
        st.dataframe(alarms_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No alarms logged for this event.")
    st.caption("Source: `historian_data:alarm_history_log`")

st.divider()

# ---------------------------------------------------------------- Row 4: feedback quality tracker
st.subheader("Suggestion Quality Tracker (operator feedback log)")
log_df = pd.read_sql_query("SELECT * FROM feedback_log ORDER BY id DESC LIMIT 50", conn)
if not log_df.empty:
    acc_rate = (log_df.user_response == "ACCEPTED").mean() * 100
    m1, m2, m3 = st.columns(3)
    m1.metric("Total suggestions logged", len(log_df))
    m2.metric("Acceptance rate", f"{acc_rate:.0f}%")
    m3.metric("Rejected", int((log_df.user_response == "REJECTED").sum()))
    st.dataframe(log_df[["timestamp", "event_id", "suggestion_type", "source", "user_response"]], use_container_width=True, hide_index=True)
else:
    st.info("No feedback logged yet — use the Accept/Reject buttons above.")
