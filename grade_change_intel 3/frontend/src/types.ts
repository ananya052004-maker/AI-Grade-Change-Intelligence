export interface Attribution {
  feature: string;
  shap_value: number;
  direction: string;
}

export interface Trajectory {
  t_s: number[];
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface RiskAssessment {
  transition_id: string;
  ts: string;
  p_offspec: Record<string, number>;
  trajectory: Trajectory | null;
  state: string;
  reason: string | null;
  attribution: Attribution[];
  model_version: string;
  calibrated: boolean;
  staleness_penalised: boolean;
}

export interface Source {
  type: string;
  reference: string;
  weight: number;
  confidence: number;
}

export interface CandidateSuggestion {
  tag: string;
  from_value: number;
  to_value: number;
  ramp_rate: number;
  predicted_effect: Record<string, unknown>;
  feasible: boolean;
  binding_constraint: string | null;
}

export interface Suggestion {
  id: string;
  transition_id: string;
  ts_issued: string;
  type: string;
  candidates: CandidateSuggestion[];
  sources: Source[];
  rationale_text: string;
  confidence: number;
  model_version: string;
  ttl_s: number;
  expires_at: string;
}

export interface DataHealth {
  missing_required_tags: string[];
  stale_tags: string[];
  clamped_tags: string[];
  prediction_disabled: boolean;
  confidence_penalty: number;
}

export interface SimilarTransition {
  transition_id: string;
  outcome: string;
}

export interface BusinessImpact {
  minutes_saved: number;
  broke_tonnes_avoided: number;
  estimated_value_usd: number;
  cost_per_tonne_usd: number;
  production_rate_tonnes_per_min: number;
  baseline_t_stab_s: number | null;
  recommended_t_stab_s: number | null;
  basis: string;
  cost_assumption: string;
}

export interface TickSnapshot {
  event_id: string;
  t_sec: number;
  phase: string;
  grade_from: string;
  grade_to: string;
  current_values: Record<string, number>;
  saturation: Record<string, boolean>;
  similar_transitions: SimilarTransition[];
  business_impact: BusinessImpact | null;
  bw_meas: number;
  bw_sp: number;
  bw_deviation_pct: number;
  risk: RiskAssessment;
  suggestion: Suggestion | null;
  no_suggestion_reason: string | null;
  data_health: DataHealth;
}

export interface TimelineEvent {
  t_sec: number;
  type: "ALARM" | "OPERATOR_ACTION" | "SUGGESTION";
  label: string;
}

export interface WhatIfResult {
  event_id: string;
  t_sec: number;
  overrides: Record<string, number>;
  baseline_risk: RiskAssessment;
  whatif_risk: RiskAssessment;
  baseline_trajectory: Trajectory;
  whatif_trajectory: Trajectory;
  feasibility: CandidateSuggestion[];
}

export interface TransitionSummary {
  transition_id: string;
  grade_from: string;
  grade_to: string;
  outcome: string;
  fault_injected: string;
  stabilization_time_sec: number | null;
  chained: boolean;
  confounded: boolean;
}

export interface CorrelationItem {
  tag: string;
  lag_s: number;
  strength: number;
  effect_size: number;
  novel: boolean;
  known_relationship_ref: string | null;
  support_n: number;
  q_value: number;
  impact_gsm: number | null;
  impact_t_stab_s: number | null;
  projection: { assumption: string; projected_relationship: string } | null;
  label: string;
  passed_fdr_gate: boolean;
}

export interface TransitionHistory {
  t_sec: number[];
  bw_meas: number[];
  bw_sp: number[];
  hi_spec: number[];
  lo_spec: number[];
  final_target_bw: number;
  phase: string[];
}

export interface StabilizationImpactRow {
  variable: string;
  impact_on_stabilization_time: number;
  p_value: number;
}
