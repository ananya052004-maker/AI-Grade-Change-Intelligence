import { useEffect, useState } from "react";
import { api } from "../api";
import type { CorrelationItem } from "../types";

// UX-02: ranked correlations with lag, strength, effect size, novel/known
// badge, support count, and impact in gsm and seconds.
export function CorrelationExplorer() {
  const [items, setItems] = useState<CorrelationItem[]>([]);

  useEffect(() => {
    api.correlations().then((cs: any) => setItems(cs.items ?? []));
  }, []);

  return (
    <div className="card">
      <h3>Correlation Discovery</h3>
      <p className="muted">
        Lagged cross-correlation (0-300s) of every candidate variable's ramp-window aggressiveness against
        |BW deviation|, gated by Benjamini-Hochberg FDR correction, minimum support (n&ge;10), and
        temporal stability (FR-23..25). Rows highlighted are flagged NOVEL -- not in the current QCS loop
        definition (config/known_relationships.yaml) -- candidates for new control logic or operator SOPs.
      </p>
      <table>
        <thead>
          <tr>
            <th>Variable</th><th>Known / Novel</th><th>Lag (s)</th><th>Strength (r)</th>
            <th>Support (n)</th><th>q-value</th><th>Impact (|dev|, gsm)</th><th>Impact (t_stab, s)</th><th>FDR gate</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.tag} className={it.novel ? "highlight-row" : ""}>
              <td><code>{it.tag}</code></td>
              <td>{it.known_relationship_ref ? `known: ${it.known_relationship_ref}` : it.novel ? "NOVEL" : "--"}</td>
              <td>{it.lag_s}</td>
              <td>{it.strength.toFixed(3)}</td>
              <td>{it.support_n}</td>
              <td>{it.q_value.toFixed(4)}</td>
              <td>{it.impact_gsm != null ? it.impact_gsm.toFixed(2) : "--"}</td>
              <td>{it.impact_t_stab_s != null ? it.impact_t_stab_s.toFixed(3) : "--"}</td>
              <td>{it.passed_fdr_gate ? "pass" : "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
