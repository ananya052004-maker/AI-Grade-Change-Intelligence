import { useEffect, useState } from "react";
import { api } from "../api";

// UX-05: full suggestion history with sources, responses, realised effects,
// and acceptance-rate trend (FR-35).
export function SuggestionLogView() {
  const [quality, setQuality] = useState<any>(null);
  const [log, setLog] = useState<any[]>([]);

  function refresh() {
    api.feedbackQuality().then(setQuality);
    api.feedbackLog().then((rows) => setLog(rows as any[]));
  }

  useEffect(() => { refresh(); const id = setInterval(refresh, 5000); return () => clearInterval(id); }, []);

  return (
    <div>
      <div className="card">
        <h3>Suggestion Quality Tracker</h3>
        {quality && quality.total > 0 ? (
          <div className="grid-2b">
            <div><div className="muted">Total suggestions</div><div style={{ fontSize: 24, fontWeight: 700 }}>{quality.total}</div></div>
            <div><div className="muted">Acceptance rate</div><div style={{ fontSize: 24, fontWeight: 700 }}>{(quality.acceptance_rate * 100).toFixed(0)}%</div></div>
            <div><div className="muted">Accepted</div><div style={{ fontSize: 24, fontWeight: 700, color: "var(--status-good)" }}>{quality.accepted}</div></div>
            <div><div className="muted">Rejected / Expired</div><div style={{ fontSize: 24, fontWeight: 700, color: "var(--status-critical)" }}>{quality.rejected} / {quality.expired}</div></div>
          </div>
        ) : (
          <p className="muted">No feedback logged yet -- accept/reject a suggestion in the Live Transition view.</p>
        )}
      </div>

      <div className="card">
        <h3>Feedback Log (append-only, hash-chained audit trail)</h3>
        <table>
          <thead><tr><th>Suggestion</th><th>Transition</th><th>Type</th><th>Issued</th><th>Response</th><th>Reject reason</th><th>Model</th></tr></thead>
          <tbody>
            {log.map((r) => (
              <tr key={r.suggestion_id}>
                <td><code>{r.suggestion_id}</code></td>
                <td>{r.transition_id}</td>
                <td>{r.type}</td>
                <td className="muted">{r.ts_issued?.slice(0, 19)}</td>
                <td>{r.response ?? "pending"}</td>
                <td>{r.reject_reason ?? "--"}</td>
                <td>{r.model_version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
