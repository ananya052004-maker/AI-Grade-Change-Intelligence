import { useEffect, useState } from "react";
import { api } from "../api";
import type { TimelineEvent } from "../types";

const TYPE_COLOR: Record<string, string> = {
  ALARM: "var(--status-critical)",
  OPERATOR_ACTION: "var(--series-1)",
  SUGGESTION: "var(--status-good)",
};

// Merges alarm history + operator actions (site data the brief calls out as
// underused) with this event's own suggestion log into one chronological view.
export function EventTimeline({ eventId, refreshKey }: { eventId: string; refreshKey?: number }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    if (!eventId) return;
    api.timeline(eventId).then((data) => setEvents(data as TimelineEvent[]));
    // refreshKey is bumped right after an Accept/Reject so the new
    // SUGGESTION entry shows up here without waiting for the next tick.
  }, [eventId, refreshKey]);

  return (
    <div className="card" id="event-timeline-section">
      <h3>Event Timeline</h3>
      <p className="muted">Alarms, operator setpoint nudges, and suggestions issued for this transition, in order.</p>
      {events.length === 0 && <p className="muted">No timeline events recorded for this transition.</p>}
      <div style={{ maxHeight: 260, overflowY: "auto" }}>
        {events.map((e, i) => (
          <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "4px 0", borderBottom: "1px solid var(--gridline)" }}>
            <span className="muted" style={{ width: 56, flexShrink: 0, textAlign: "right" }}>{e.t_sec.toFixed(0)}s</span>
            <span className="source-chip" style={{ borderColor: TYPE_COLOR[e.type], color: TYPE_COLOR[e.type], flexShrink: 0 }}>
              {e.type.replace("_", " ")}
            </span>
            <span className="secondary" style={{ fontSize: 13 }}>{e.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
