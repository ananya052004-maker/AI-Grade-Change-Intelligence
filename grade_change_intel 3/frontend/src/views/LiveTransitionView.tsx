import { useEffect, useMemo, useState } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { api } from "../api";
import type { TickSnapshot, TransitionHistory, TransitionSummary } from "../types";
import { RiskBadge } from "../components/RiskBadge";
import { SourceChips } from "../components/SourceChips";
import { DataHealthBanner } from "../components/DataHealthBanner";
import { EventTimeline } from "../components/EventTimeline";
import { WhatIfSimulator } from "../components/WhatIfSimulator";
import { Copilot } from "../components/Copilot";
import { ReplayStory } from "../components/ReplayStory";

export function LiveTransitionView({ onNavigateToLog }: { onNavigateToLog?: () => void }) {
  const [transitions, setTransitions] = useState<TransitionSummary[]>([]);
  const [eventId, setEventId] = useState<string>("");
  const [maxT, setMaxT] = useState(1000);
  const [tSec, setTSec] = useState(0);
  const [history, setHistory] = useState<TransitionHistory | null>(null);
  const [snapshot, setSnapshot] = useState<TickSnapshot | null>(null);
  const [operatorId] = useState("OP01");
  const [live, setLive] = useState(false);
  const [respondedId, setRespondedId] = useState<string | null>(null);
  const [respondedStatus, setRespondedStatus] = useState<"ACCEPTED" | "REJECTED" | null>(null);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [replayOpen, setReplayOpen] = useState(false);

  useEffect(() => {
    api.listTransitions().then((data) => {
      const list = data as TransitionSummary[];
      setTransitions(list);
      if (list.length) setEventId(list[3]?.transition_id ?? list[0].transition_id);
    });
  }, []);

  useEffect(() => {
    if (!eventId) return;
    api.getTransition(eventId).then((meta: any) => {
      setMaxT(meta.max_t_sec);
      setTSec(Math.min(440, meta.max_t_sec));
    });
    api.history(eventId).then((h) => setHistory(h as TransitionHistory));
  }, [eventId]);

  useEffect(() => {
    if (!eventId || live) return;
    // Debounced: the range input fires onChange continuously while dragging,
    // and firing a tick request per pixel both floods the backend and (with
    // enough overlap) can race concurrent model-inference calls. One request
    // per pause in dragging is all the UI actually needs.
    const timer = setTimeout(() => {
      api.tick(eventId, tSec).then((s) => setSnapshot(s as TickSnapshot));
    }, 150);
    return () => clearTimeout(timer);
  }, [eventId, tSec, live]);

  useEffect(() => {
    if (!live || !eventId) return;
    const ws = new WebSocket(api.wsUrl(eventId, 15));
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.done || data.error) { setLive(false); return; }
      setSnapshot(data as TickSnapshot);
      setTSec(data.t_sec);
    };
    ws.onclose = () => setLive(false);
    return () => ws.close();
  }, [live, eventId]);

  const chartData = useMemo(() => {
    if (!history) return [];
    const rows = history.t_sec.map((t, i) => ({
      t_sec: t, bw_meas: t <= tSec ? history.bw_meas[i] : null,
      bw_sp: history.bw_sp[i], hi_spec: history.hi_spec[i], lo_spec: history.lo_spec[i],
      band: history.hi_spec[i] - history.lo_spec[i],
    }));
    if (snapshot?.risk.trajectory) {
      const traj = snapshot.risk.trajectory;
      traj.t_s.forEach((dt, i) => {
        rows.push({
          t_sec: tSec + dt, bw_meas: null, bw_sp: NaN, hi_spec: NaN, lo_spec: NaN, band: NaN,
          // @ts-expect-error extra projected fields
          p50: traj.p50[i], p10: traj.p10[i], p90: traj.p90[i], projBand: traj.p90[i] - traj.p10[i],
        });
      });
    }
    return rows;
  }, [history, snapshot, tSec]);

  async function respond(response: "ACCEPTED" | "REJECTED") {
    if (!snapshot?.suggestion) return;
    await api.submitFeedback({
      suggestion_id: snapshot.suggestion.id, response, operator_id: operatorId,
      reject_reason: response === "REJECTED" ? "DISAGREE_WITH_DIAGNOSIS" : undefined,
    });
    setRespondedId(snapshot.suggestion.id);
    setRespondedStatus(response);
    setTimelineRefreshKey((k) => k + 1); // Event Timeline refetches and shows this response immediately
    setTimeout(() => {
      const el = document.getElementById("event-timeline-section");
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.classList.add("flash-highlight");
      setTimeout(() => el?.classList.remove("flash-highlight"), 1600);
    }, 300); // give the timeline a moment to refetch before scrolling to it
  }

  // Source chips are a shortcut to the evidence they cite: CORRELATION_MODEL
  // -> the SHAP breakdown driving the risk score, HISTORICAL_ANALOG -> the
  // similar-past-transitions list this recommendation was built from.
  function jumpToEvidence(sourceType: string) {
    const targetId = sourceType === "CORRELATION_MODEL" ? "shap-section"
      : sourceType === "HISTORICAL_ANALOG" ? "similar-transitions-section"
      : null;
    if (!targetId) return;
    const el = document.getElementById(targetId);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("flash-highlight");
    setTimeout(() => el.classList.remove("flash-highlight"), 1600);
  }

  return (
    <div>
      <div className="card" style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Transition:{" "}
          <select value={eventId} onChange={(e) => { setEventId(e.target.value); setLive(false); }}>
            {transitions.map((t) => (
              <option key={t.transition_id} value={t.transition_id}>
                {t.transition_id} | {t.grade_from}→{t.grade_to} | {t.outcome}
                {t.fault_injected ? ` | ${t.fault_injected}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label style={{ flex: 1 }}>
          Replay position: {tSec}s / {maxT}s
          <input type="range" min={0} max={maxT} step={5} value={tSec} disabled={live}
                 onChange={(e) => setTSec(Number(e.target.value))} style={{ width: "100%" }} />
        </label>
        <button className="btn" onClick={() => setLive((v) => !v)}>{live ? "Stop live" : "Play live (WebSocket)"}</button>
        <button className="btn" onClick={() => { setLive(false); setReplayOpen(true); }} disabled={!history}>
          ▶ Replay Transition
        </button>
      </div>

      {snapshot && <DataHealthBanner health={snapshot.data_health} />}

      <div className="grid-2">
        <div className="card">
          <h3>Basis Weight -- Trend, Spec Band & Projected Trajectory</h3>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData} margin={{ left: 8, right: 8 }}>
              <CartesianGrid stroke="var(--gridline)" vertical={false} />
              <XAxis dataKey="t_sec" stroke="var(--text-muted)" fontSize={12} label={{ value: "Time (s)", position: "insideBottom", offset: -4, fontSize: 11 }} />
              <YAxis stroke="var(--text-muted)" fontSize={12} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area dataKey="lo_spec" stackId="spec" stroke="none" fill="transparent" isAnimationActive={false} />
              <Area dataKey="band" stackId="spec" stroke="none" fill="var(--series-band)" fillOpacity={0.35} name="+-2.5% spec band" isAnimationActive={false} />
              <Line dataKey="bw_sp" stroke="var(--baseline)" strokeDasharray="4 3" dot={false} name="Setpoint trajectory" isAnimationActive={false} />
              <Line dataKey="bw_meas" stroke="var(--series-1)" strokeWidth={2} dot={false} name="Actual Basis Weight" isAnimationActive={false} connectNulls={false} />
              <Line dataKey="p50" stroke="var(--series-2)" strokeWidth={2} strokeDasharray="5 3" dot={false} name="Projected (P50)" isAnimationActive={false} />
              <ReferenceLine y={history?.final_target_bw} stroke="var(--status-good)" strokeDasharray="2 2" label={{ value: "Final target", fontSize: 10, fill: "var(--text-muted)" }} />
              <ReferenceLine x={tSec} stroke="var(--text-muted)" strokeDasharray="2 2" />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="muted">Band shading is the +-2.5% off-spec threshold around the Controller's live ramping setpoint (Sec 1.3), not the final grade target.</p>
        </div>

        <div className="card">
          <h3>Off-Spec Risk</h3>
          {snapshot && (
            <>
              <RiskBadge state={snapshot.risk.state} />
              <div style={{ fontSize: 32, fontWeight: 700, margin: "8px 0" }}>
                {snapshot.risk.state === "NO_PREDICTION" ? "--" : `${((snapshot.risk.p_offspec["180"] ?? 0) * 100).toFixed(1)}%`}
              </div>
              <p className="muted">P(sustained off-spec within {180}s) &mdash; also computed at 60s: {((snapshot.risk.p_offspec["60"] ?? 0) * 100).toFixed(1)}%, 300s: {((snapshot.risk.p_offspec["300"] ?? 0) * 100).toFixed(1)}%</p>
              {snapshot.risk.reason && <p className="muted">Reason: {snapshot.risk.reason}</p>}
              <div id="shap-section">
                <h4 style={{ fontSize: 13, marginBottom: 4 }}>Top SHAP contributors (FR-20)</h4>
                {snapshot.risk.attribution.map((a) => (
                  <div key={a.feature} className="secondary" style={{ fontSize: 12, marginBottom: 2 }}>
                    <code>{a.feature}</code> &mdash; {a.direction} ({a.shap_value >= 0 ? "+" : ""}{a.shap_value.toFixed(3)})
                  </div>
                ))}
                <p className="muted">Source: <code>model_shap:{snapshot.risk.model_version}</code></p>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Recommended Setpoints</h3>
        {snapshot?.suggestion ? (
          <>
            <table>
              <thead><tr><th>Handle</th><th>Current</th><th>Recommended</th><th>Feasible</th><th>Binding constraint</th></tr></thead>
              <tbody>
                {snapshot.suggestion.candidates.map((c) => (
                  <tr key={c.tag} className={!c.feasible ? "highlight-row" : ""}>
                    <td>{c.tag}</td>
                    <td>{c.from_value.toFixed(2)}</td>
                    <td>{c.to_value.toFixed(2)}</td>
                    <td>{c.feasible ? "yes" : "SUPPRESSED"}</td>
                    <td>{c.binding_constraint ?? "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="secondary" style={{ fontSize: 13 }}>{snapshot.suggestion.rationale_text}</p>
            <SourceChips sources={snapshot.suggestion.sources} onChipClick={jumpToEvidence} />
            {respondedId === snapshot.suggestion.id ? (
              <p style={{ marginTop: 10, fontWeight: 600, color: respondedStatus === "ACCEPTED" ? "var(--status-good)" : "var(--status-critical)" }}>
                {respondedStatus === "ACCEPTED" ? "✓ Accepted" : "✗ Rejected"} -- logged to the audit trail, now showing in the Event Timeline below.{" "}
                {onNavigateToLog && (
                  <a href="#" className="secondary" style={{ fontWeight: 400 }}
                     onClick={(e) => { e.preventDefault(); onNavigateToLog(); }}>
                    View full history in Suggestion Log &rarr;
                  </a>
                )}
              </p>
            ) : (
              <div style={{ marginTop: 10 }}>
                <button className="btn accept" onClick={() => respond("ACCEPTED")}>Accept</button>
                <button className="btn reject" onClick={() => respond("REJECTED")}>Reject</button>
              </div>
            )}
          </>
        ) : (
          <p className="muted">No active suggestion{snapshot?.no_suggestion_reason ? ` (${snapshot.no_suggestion_reason})` : ""}.</p>
        )}
      </div>

      <div className="grid-2b">
        <div className="card">
          <h3>Business Impact</h3>
          <p className="muted">
            Comparing the fastest-stabilizing-tercile historical setpoints against this grade pair's plain
            historical median. Dollar figure is a stated market-price assumption, not a precise broke cost.
          </p>
          {snapshot?.business_impact ? (
            <div className="grid-2b">
              <div>
                <div className="muted">Minutes saved</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: snapshot.business_impact.minutes_saved > 0 ? "var(--status-good)" : "var(--text-primary)" }}>
                  {snapshot.business_impact.minutes_saved.toFixed(1)}
                </div>
              </div>
              <div>
                <div className="muted">Broke avoided (tonnes)</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: snapshot.business_impact.broke_tonnes_avoided > 0 ? "var(--status-good)" : "var(--text-primary)" }}>
                  {snapshot.business_impact.broke_tonnes_avoided.toFixed(2)}
                </div>
              </div>
              <div style={{ gridColumn: "1 / -1" }}>
                <div className="muted">Estimated value</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: snapshot.business_impact.estimated_value_usd > 0 ? "var(--status-good)" : "var(--text-primary)" }}>
                  ${snapshot.business_impact.estimated_value_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <p className="muted" style={{ marginTop: 4 }}>
                  At {snapshot.business_impact.production_rate_tonnes_per_min.toFixed(2)} t/min current production rate,
                  ${snapshot.business_impact.cost_per_tonne_usd.toFixed(0)}/tonne assumed.{" "}
                  {snapshot.business_impact.baseline_t_stab_s != null &&
                    `Baseline stabilization: ${snapshot.business_impact.baseline_t_stab_s}s -> recommended: ${snapshot.business_impact.recommended_t_stab_s}s.`}
                </p>
                <p className="muted" style={{ marginTop: 2, fontSize: 11 }}>{snapshot.business_impact.cost_assumption}</p>
              </div>
            </div>
          ) : (
            <p className="muted">Not enough historical data for this grade pair to estimate impact.</p>
          )}
        </div>

        <div className="card" id="similar-transitions-section">
          <h3>Similar Historical Transitions</h3>
          <p className="muted">The nearest historical analogs this recommendation is based on (FR-21).</p>
          {snapshot && snapshot.similar_transitions.length > 0 ? (
            <table>
              <thead><tr><th>Transition</th><th>Outcome</th></tr></thead>
              <tbody>
                {snapshot.similar_transitions.map((s) => (
                  <tr key={s.transition_id}>
                    <td><code>{s.transition_id}</code></td>
                    <td>{s.outcome}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No similar historical transitions found yet.</p>
          )}
        </div>
      </div>

      {snapshot && (
        <WhatIfSimulator eventId={eventId} tSec={tSec} currentValues={snapshot.current_values} />
      )}

      {eventId && <EventTimeline eventId={eventId} refreshKey={timelineRefreshKey} />}

      {!copilotOpen && (
        <button className="copilot-toggle-btn" onClick={() => setCopilotOpen(true)} aria-label="Open Copilot" title="Open Copilot">
          🤖
        </button>
      )}
      <div className={`copilot-drawer ${copilotOpen ? "open" : ""}`}>
        <Copilot snapshot={snapshot} onClose={() => setCopilotOpen(false)} />
      </div>

      <ReplayStory
        open={replayOpen} onClose={() => setReplayOpen(false)} history={history} snapshot={snapshot}
        onSeek={(t) => setTSec(t)}
      />
    </div>
  );
}
