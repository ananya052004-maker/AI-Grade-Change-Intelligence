// UX-07: colour MUST NOT be the sole carrier of risk state -- state text and
// a shape (the dot + distinct label) accompany colour.
const STATE_META: Record<string, { color: string; label: string }> = {
  OK: { color: "var(--status-good)", label: "OK" },
  WATCH: { color: "var(--status-warning)", label: "WATCH" },
  AT_RISK: { color: "var(--status-serious)", label: "AT RISK" },
  CRITICAL: { color: "var(--status-critical)", label: "CRITICAL" },
  NO_PREDICTION: { color: "var(--text-muted)", label: "NO PREDICTION" },
  LOW_CONFIDENCE: { color: "var(--text-muted)", label: "LOW CONFIDENCE" },
};

export function RiskBadge({ state }: { state: string }) {
  const meta = STATE_META[state] ?? { color: "var(--text-muted)", label: state };
  return (
    <span className="risk-badge" style={{ color: meta.color, borderColor: meta.color }}>
      <span className="risk-dot" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}
