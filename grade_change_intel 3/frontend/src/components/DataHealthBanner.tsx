import type { DataHealth } from "../types";

// UX-08: the dashboard MUST degrade visibly, not silently -- names any
// stale/missing tag and the resulting capability loss.
export function DataHealthBanner({ health }: { health: DataHealth }) {
  const issues: string[] = [];
  if (health.missing_required_tags.length) {
    issues.push(`Missing required tags: ${health.missing_required_tags.join(", ")} -- predictions disabled.`);
  }
  if (health.stale_tags.length) {
    issues.push(`Stale tags (forward-filled beyond tolerance): ${health.stale_tags.join(", ")}.`);
  }
  if (health.clamped_tags.length) {
    issues.push(`Clamped out-of-range readings: ${health.clamped_tags.join(", ")}.`);
  }
  if (health.confidence_penalty > 0) {
    issues.push(`Confidence penalised ${(health.confidence_penalty * 100).toFixed(0)}% for data staleness.`);
  }
  if (issues.length === 0) return null;
  return (
    <div className="data-health-banner">
      <strong>Data health:</strong> {issues.join(" ")}
    </div>
  );
}
