import { useEffect, useRef, useState } from "react";
import type { TickSnapshot, TransitionHistory } from "../types";
import { buildChapters, Chapter } from "../replayStory";

const CHAPTER_DURATION_MS = 4000;

// Tells the story of ONE transition as a sequence of narrated chapters
// instead of a raw chart -- but it does this by driving the SAME tSec state
// the manual slider already drives (via onSeek), so the existing tick-fetch
// effect in LiveTransitionView does the actual data fetching. This component
// adds narration on top of data that's already real and already flowing
// through the existing pipeline; it doesn't introduce a second source of truth.
export function ReplayStory({
  open, onClose, history, snapshot, onSeek,
}: {
  open: boolean;
  onClose: () => void;
  history: TransitionHistory | null;
  snapshot: TickSnapshot | null;
  onSeek: (tSec: number) => void;
}) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open || !history) return;
    const ch = buildChapters(history);
    setChapters(ch);
    setIndex(0);
    setPlaying(true);
    if (ch.length) onSeek(ch[0].t_sec);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, history]);

  useEffect(() => {
    if (!open || !playing || chapters.length === 0 || index >= chapters.length - 1) return;
    timerRef.current = setTimeout(() => {
      const next = index + 1;
      setIndex(next);
      onSeek(chapters[next].t_sec);
    }, CHAPTER_DURATION_MS);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, playing, index, chapters]);

  if (!open) return null;

  function goTo(i: number) {
    if (i < 0 || i >= chapters.length) return;
    setPlaying(false);
    setIndex(i);
    onSeek(chapters[i].t_sec);
  }

  const chapter = chapters[index];

  function narrate(): string {
    if (!chapter) return "";
    if (!snapshot) return "Loading...";
    const p180 = ((snapshot.risk.p_offspec["180"] ?? 0) * 100).toFixed(1);
    switch (chapter.title) {
      case "Everything Normal":
        return `Basis Weight steady at ${snapshot.bw_meas.toFixed(1)} gsm, tracking the setpoint closely. Risk: ${snapshot.risk.state.replace("_", " ")}.`;
      case "Grade Change Begins":
        return `The grade change ramp starts -- setpoints move toward the new target. Current deviation: ${snapshot.bw_deviation_pct >= 0 ? "+" : ""}${snapshot.bw_deviation_pct.toFixed(2)}%.`;
      case "Risk Increasing":
        return snapshot.risk.state === "NO_PREDICTION"
          ? `No prediction available here: ${snapshot.risk.reason ?? "data quality issue"}.`
          : `Off-spec risk reaches ${p180}% within the next 3 minutes. Top driver: ${snapshot.risk.attribution[0]?.feature ?? "n/a"}.`;
      case "AI Steps In":
        return snapshot.suggestion
          ? snapshot.suggestion.rationale_text
          : `No recommendation was issued at this point${snapshot.no_suggestion_reason ? ` (${snapshot.no_suggestion_reason.toLowerCase().replace(/_/g, " ")})` : ""} -- not every risky moment needs a new setpoint change.`;
      case "Resolved":
        return `Basis Weight ends at ${snapshot.bw_meas.toFixed(1)} gsm vs a ${snapshot.bw_sp.toFixed(1)} gsm target. Final state: ${snapshot.risk.state.replace("_", " ")}.`;
      default:
        return "";
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}
    >
      <div className="card" style={{ width: 520, maxWidth: "90vw" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>▶ Replay Transition</h3>
          <button onClick={onClose} aria-label="Close replay"
                  style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "var(--text-muted)" }}>
            &times;
          </button>
        </div>

        <div style={{ display: "flex", gap: 6, margin: "16px 0 14px" }}>
          {chapters.map((c, i) => (
            <div key={i} onClick={() => goTo(i)} title={c.title}
                 style={{ flex: 1, height: 4, borderRadius: 2, cursor: "pointer", background: i <= index ? "var(--series-1)" : "var(--gridline)" }} />
          ))}
        </div>

        {chapter ? (
          <>
            <p className="muted" style={{ marginBottom: 2 }}>
              ~{Math.max(1, Math.round(chapter.t_sec / 60))} min in ({chapter.t_sec.toFixed(0)}s) &middot; chapter {index + 1} of {chapters.length}
            </p>
            <h4 style={{ marginTop: 0 }}>{chapter.title}</h4>
            <p className="secondary" style={{ minHeight: 44 }}>{narrate()}</p>
          </>
        ) : (
          <p className="muted">Loading transition data...</p>
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="btn" onClick={() => goTo(index - 1)} disabled={index === 0}>&larr; Prev</button>
          <button className="btn" onClick={() => setPlaying((p) => !p)} disabled={index >= chapters.length - 1}>
            {playing ? "Pause" : "Play"}
          </button>
          <button className="btn" onClick={() => goTo(index + 1)} disabled={index >= chapters.length - 1}>Next &rarr;</button>
        </div>
      </div>
    </div>
  );
}
