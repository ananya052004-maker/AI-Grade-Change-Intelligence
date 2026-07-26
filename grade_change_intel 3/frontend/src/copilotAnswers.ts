import type { TickSnapshot } from "./types";

// Template-based Copilot: every answer is assembled from fields already
// present on the current TickSnapshot -- the same data already rendered
// elsewhere on this screen, just phrased conversationally. Deliberately NOT
// a real LLM call: no external API, no network dependency, and no risk of
// answering with something ungrounded, which matches the same rule the rest
// of this system already follows (FR-22 -- rationale generated only from
// structured sources[], never free-floating text).

interface Pattern {
  test: RegExp;
  answer: (s: TickSnapshot) => string;
}

const PATTERNS: Pattern[] = [
  {
    test: /help|what can|example/,
    answer: () =>
      'Try asking: "why is this risky?", "what should I do?", "how much can this save?", ' +
      '"similar transitions?", "is it safe?", or "what\'s happening right now?"',
  },
  {
    test: /why.*risk|risk.*why|driver|drives|cause/,
    answer: (s) => {
      if (s.risk.state === "NO_PREDICTION") return `No prediction right now: ${s.risk.reason ?? "a data quality issue"}.`;
      if (s.risk.attribution.length === 0) return "No specific risk drivers to report at this moment.";
      const [top, second] = s.risk.attribution;
      let out = `The biggest driver right now is \`${top.feature}\`, which ${top.direction} (impact ${top.shap_value >= 0 ? "+" : ""}${top.shap_value.toFixed(3)})`;
      if (second) out += `, with \`${second.feature}\` also contributing`;
      return out + ". Full breakdown is in the Off-Spec Risk panel above.";
    },
  },
  {
    test: /how risk|risk level|risk %|risk percent|what.*risk\b/,
    answer: (s) => {
      if (s.risk.state === "NO_PREDICTION") return `No prediction available: ${s.risk.reason ?? "data quality issue"}.`;
      const p180 = (s.risk.p_offspec["180"] ?? 0) * 100;
      return `Current state is ${s.risk.state.replace("_", " ")}, with a ${p180.toFixed(1)}% chance of sustained off-spec within the next 3 minutes.`;
    },
  },
  {
    test: /what should i do|recommend|advice|action|handle/,
    answer: (s) => {
      if (!s.suggestion) return `No active recommendation right now${s.no_suggestion_reason ? ` (${s.no_suggestion_reason.toLowerCase().replace(/_/g, " ")})` : ""}.`;
      return `${s.suggestion.rationale_text} See the Recommended Setpoints table for exact values.`;
    },
  },
  {
    test: /safe|feasible|allowed|within limit/,
    answer: (s) => {
      if (!s.suggestion) return "No active recommendation to check right now.";
      const infeasible = s.suggestion.candidates.filter((c) => !c.feasible);
      if (infeasible.length === 0) return "Yes -- every value in the current recommendation is within recipe and actuator limits.";
      const list = infeasible.map((c) => `${c.tag} (${c.binding_constraint})`).join(", ");
      return `Not entirely: ${list} would violate a limit, so that part of the recommendation is suppressed, not silently clipped.`;
    },
  },
  {
    test: /save|impact|broke|waste|money|tonne|minute/,
    answer: (s) => {
      if (!s.business_impact) return "Not enough historical data for this grade pair to estimate business impact.";
      const b = s.business_impact;
      if (b.minutes_saved <= 0) return "No measurable time/waste savings estimated for this grade pair right now.";
      return `Following the recommendation could save about ${b.minutes_saved.toFixed(1)} minutes and avoid roughly ${b.broke_tonnes_avoided.toFixed(2)} tonnes of broke (~$${b.estimated_value_usd.toLocaleString()} at $${b.cost_per_tonne_usd.toFixed(0)}/tonne), based on this grade pair's history.`;
    },
  },
  {
    test: /similar|before|analog|past transition/,
    answer: (s) => {
      if (s.similar_transitions.length === 0) return "No similar historical transitions found yet.";
      const list = s.similar_transitions.map((t) => `${t.transition_id} (${t.outcome})`).join(", ");
      return `This is based on ${s.similar_transitions.length} similar past transitions: ${list}.`;
    },
  },
  {
    test: /happening|status|current|now\??$|basis weight|\bbw\b/,
    answer: (s) => {
      const phase = s.phase.replace("Phase.", "");
      return `Basis Weight is currently ${s.bw_meas.toFixed(1)} gsm vs a setpoint of ${s.bw_sp.toFixed(1)} gsm (${s.bw_deviation_pct >= 0 ? "+" : ""}${s.bw_deviation_pct.toFixed(2)}% deviation), in the ${phase} phase.`;
    },
  },
  {
    test: /alarm|operator action|timeline/,
    answer: () => "Alarms and operator actions for this transition are logged in the Event Timeline card further down the page.",
  },
];

export function answerQuestion(question: string, snapshot: TickSnapshot | null): string {
  if (!snapshot) return "Pick a transition first -- I don't have any live data to answer from yet.";
  const q = question.toLowerCase();
  for (const p of PATTERNS) {
    if (p.test.test(q)) return p.answer(snapshot);
  }
  return 'I can only answer questions grounded in the data already on this screen. Try asking about risk, ' +
    'the recommendation, similar transitions, or business impact -- or type "help" for examples.';
}

export const SUGGESTED_QUESTIONS = [
  "Why is this risky?",
  "What should I do?",
  "How much can this save?",
  "Similar transitions?",
  "What's happening right now?",
];
