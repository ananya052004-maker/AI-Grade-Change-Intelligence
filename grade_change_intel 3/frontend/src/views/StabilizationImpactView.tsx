import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { api } from "../api";
import type { StabilizationImpactRow } from "../types";

// UX-04: loops/parameters ranked by contribution to T_stab, with
// historically-fastest-stabilizing setpoint suggestions per grade pair
// (the latter surfaces in the Live Transition view's suggestion panel,
// sourced from the same fastest-stabilizing-half analog bias).
export function StabilizationImpactView() {
  const [rows, setRows] = useState<StabilizationImpactRow[]>([]);

  useEffect(() => {
    api.stabilizationImpact().then((data) => setRows(data as StabilizationImpactRow[]));
  }, []);

  return (
    <div className="card">
      <h3>Stabilization Impact Ranking</h3>
      <p className="muted">
        Correlates each variable's ramp-window aggressiveness (std of rate-of-change) against
        stabilization_time_sec (Sec 2.4 definition: within +-1% of final target, held 120s) &mdash; FR-29.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} layout="vertical" margin={{ left: 24 }}>
          <CartesianGrid stroke="var(--gridline)" horizontal={false} />
          <XAxis type="number" stroke="var(--text-muted)" fontSize={12} domain={[-1, 1]} />
          <YAxis type="category" dataKey="variable" stroke="var(--text-muted)" fontSize={12} width={120} />
          <Tooltip contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", fontSize: 12 }}
                   formatter={(v: number) => v.toFixed(3)} />
          <Bar dataKey="impact_on_stabilization_time" name="impact (r)">
            {rows.map((r, i) => (
              <Cell key={i} fill={r.impact_on_stabilization_time >= 0 ? "var(--series-2)" : "var(--series-1)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <table>
        <thead><tr><th>Variable</th><th>Impact (r)</th><th>p-value</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.variable}>
              <td>{r.variable}</td>
              <td>{r.impact_on_stabilization_time.toFixed(3)}</td>
              <td>{r.p_value.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
