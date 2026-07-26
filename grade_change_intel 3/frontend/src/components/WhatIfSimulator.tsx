import { useEffect, useState } from "react";
import { api } from "../api";
import type { WhatIfResult } from "../types";

const HANDLES = ["STOCK_FLOW", "FILLER_FLOW", "STEAM_PRESS_G1", "MACHINE_SPEED"];

// Interactive counterfactual: reruns the SAME trained risk + trajectory
// models with one or more setpoints hypothetically changed, so "what if I
// nudge steam pressure" gets a real model-backed answer, not a guess.
export function WhatIfSimulator({ eventId, tSec, currentValues }: {
  eventId: string; tSec: number; currentValues: Record<string, number>;
}) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Re-seed the inputs from the current process state whenever the
    // selected transition changes -- but not on every tick, so the operator
    // can keep exploring a "what if" without it resetting under them.
    const seeded: Record<string, string> = {};
    HANDLES.forEach((h) => { if (currentValues[h] != null) seeded[h] = currentValues[h].toFixed(2); });
    setOverrides(seeded);
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId]);

  async function runSimulation() {
    const numericOverrides: Record<string, number> = {};
    for (const h of HANDLES) {
      const v = parseFloat(overrides[h]);
      if (!Number.isNaN(v) && currentValues[h] != null && Math.abs(v - currentValues[h]) > 1e-6) {
        numericOverrides[h] = v;
      }
    }
    if (Object.keys(numericOverrides).length === 0) {
      alert("Change at least one setpoint value below to run a what-if.");
      return;
    }
    setLoading(true);
    try {
      const r = await api.whatif(eventId, tSec, numericOverrides);
      setResult(r as WhatIfResult);
    } finally {
      setLoading(false);
    }
  }

  function resetToCurrent() {
    const seeded: Record<string, string> = {};
    HANDLES.forEach((h) => { if (currentValues[h] != null) seeded[h] = currentValues[h].toFixed(2); });
    setOverrides(seeded);
    setResult(null);
  }

  const baselineP180 = result ? (result.baseline_risk.p_offspec["180"] ?? 0) * 100 : null;
  const whatifP180 = result ? (result.whatif_risk.p_offspec["180"] ?? 0) * 100 : null;
  const delta = baselineP180 != null && whatifP180 != null ? whatifP180 - baselineP180 : null;

  return (
    <div className="card">
      <h3>What-If Simulator</h3>
      <p className="muted">Try a hypothetical setpoint and see the model's predicted effect on off-spec risk before anyone touches the real machine.</p>
      <table>
        <thead><tr><th>Handle</th><th>Current</th><th>Try value</th></tr></thead>
        <tbody>
          {HANDLES.map((h) => (
            <tr key={h}>
              <td>{h}</td>
              <td className="muted">{currentValues[h] != null ? currentValues[h].toFixed(2) : "--"}</td>
              <td>
                <input
                  type="number" step="0.1" value={overrides[h] ?? ""}
                  onChange={(e) => setOverrides((o) => ({ ...o, [h]: e.target.value }))}
                  style={{ width: 100, padding: "3px 6px", background: "var(--page)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4 }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 10 }}>
        <button className="btn" onClick={runSimulation} disabled={loading}>{loading ? "Simulating..." : "Run what-if"}</button>
        <button className="btn" onClick={resetToCurrent}>Reset to current</button>
      </div>

      {result && (
        <div style={{ marginTop: 14 }}>
          <div className="grid-2b">
            <div>
              <div className="muted">Baseline risk (180s)</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{baselineP180?.toFixed(1)}%</div>
            </div>
            <div>
              <div className="muted">What-if risk (180s)</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: delta != null && delta < -0.5 ? "var(--status-good)" : delta != null && delta > 0.5 ? "var(--status-critical)" : "var(--text-primary)" }}>
                {whatifP180?.toFixed(1)}%
                {delta != null && Math.abs(delta) > 0.5 && (
                  <span style={{ fontSize: 13, marginLeft: 6 }}>({delta > 0 ? "+" : ""}{delta.toFixed(1)}pp)</span>
                )}
              </div>
            </div>
          </div>
          {delta != null && Math.abs(delta) <= 0.5 && (
            <p className="muted" style={{ marginTop: 6 }}>
              No meaningful change predicted for this nudge -- try a larger change, or check the Off-Spec Risk panel's
              SHAP contributors above to see which factors actually drive risk at this point in the transition.
            </p>
          )}
          {result.feasibility.some((f) => !f.feasible) && (
            <p style={{ color: "var(--status-critical)", marginTop: 6, fontSize: 13 }}>
              Not achievable as entered: {result.feasibility.filter((f) => !f.feasible).map((f) => `${f.tag} (${f.binding_constraint})`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
