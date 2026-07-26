import type { Source } from "../types";

// UX-06: every displayed suggestion MUST show its source-of-inference chips
// inline -- not hidden behind a click. (Being ALSO clickable as a shortcut to
// the underlying evidence is additive, not a substitute for that visibility.)
export function SourceChips({ sources, onChipClick }: { sources: Source[]; onChipClick?: (type: string) => void }) {
  return (
    <span>
      {sources.map((s, i) => {
        const clickable = Boolean(onChipClick);
        return (
          <span
            className="source-chip" key={i} onClick={() => onChipClick?.(s.type)}
            style={clickable ? { cursor: "pointer" } : undefined}
            title={`${s.reference} (confidence ${(s.confidence * 100).toFixed(0)}%)` + (clickable ? " -- click to jump to the evidence" : "")}
          >
            {s.type.replace(/_/g, " ")}
          </span>
        );
      })}
    </span>
  );
}
