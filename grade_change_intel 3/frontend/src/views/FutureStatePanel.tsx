import { useEffect, useState } from "react";
import { api } from "../api";
import type { CorrelationItem } from "../types";

// UX-03: for each correlated parameter trending out of range, the projected
// trajectory and predicted BW impact if the trend continues (FR-27).
export function FutureStatePanel() {
  const [items, setItems] = useState<CorrelationItem[]>([]);

  useEffect(() => {
    api.correlations().then((cs: any) => setItems((cs.items ?? []).filter((i: CorrelationItem) => i.projection)));
  }, []);

  return (
    <div className="card">
      <h3>Future State -- Projected Impact of Trending Correlations</h3>
      <p className="muted">
        Rendered for every correlation that passed the FDR gate (FR-25) and therefore represents a real,
        stable association rather than a spurious one (Sec 6.5 anti-requirement: the System never presents
        an unqualified correlation as an action driver).
      </p>
      {items.length === 0 && <p className="muted">No gated correlations trending out of range right now.</p>}
      {items.map((it) => (
        <div key={it.tag} className="card" style={{ marginBottom: 8, background: "var(--page)" }}>
          <strong>{it.tag}</strong>{it.novel && <span className="source-chip">NOVEL</span>}
          <p className="secondary" style={{ fontSize: 13, margin: "6px 0" }}>
            {it.projection?.projected_relationship}
          </p>
          <p className="muted">Assumption: {it.projection?.assumption}. Based on n={it.support_n} historical transitions, q={it.q_value.toFixed(4)}.</p>
        </div>
      ))}
    </div>
  );
}
