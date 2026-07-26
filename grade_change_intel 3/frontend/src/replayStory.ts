import type { TransitionHistory } from "./types";

// Chapter detection is pure client-side analysis of data ALREADY fetched by
// LiveTransitionView (api.history()) -- no new backend endpoint, no new API
// call. It picks 5 genuinely meaningful moments in THIS specific transition
// (not a fixed "minute 1/2/3/4/5" template, since real transitions here run
// anywhere from ~15 to ~35 minutes): the baseline, when the ramp actually
// starts, the worst moment of deviation, shortly after that (where a
// recommendation would fire if one was going to), and when it settles.

export interface Chapter {
  title: string;
  t_sec: number;
}

const TITLES = ["Everything Normal", "Grade Change Begins", "Risk Increasing", "AI Steps In", "Resolved"];

export function buildChapters(history: TransitionHistory): Chapter[] {
  const n = history.t_sec.length;
  if (n === 0) return [];

  const isPreCheck = (i: number) => history.phase[i]?.includes("PRE_CHECK");
  const isSteady = (i: number) => history.phase[i]?.includes("STEADY");
  const deviationAt = (i: number) => Math.abs(history.bw_meas[i] - history.bw_sp[i]);

  const idxStart = 0;

  let idxRampStart = history.phase.findIndex((_, i) => !isPreCheck(i));
  if (idxRampStart < 0) idxRampStart = Math.floor(n * 0.15);

  let idxPeak = idxRampStart;
  let maxDev = -Infinity;
  for (let i = idxRampStart; i < n; i++) {
    const d = deviationAt(i);
    if (d > maxDev) { maxDev = d; idxPeak = i; }
  }

  const idxResponse = Math.min(idxPeak + Math.max(2, Math.floor((n - idxPeak) * 0.15)), n - 1);

  let idxResolution = n - 1;
  for (let i = n - 1; i >= 0; i--) {
    if (isSteady(i)) { idxResolution = i; break; }
  }

  // De-dupe in case a short/simple transition collapses some of these into
  // the same sample, and keep them in time order.
  const indices = Array.from(new Set([idxStart, idxRampStart, idxPeak, idxResponse, idxResolution])).sort((a, b) => a - b);

  return indices.map((idx, i) => ({
    title: TITLES[Math.min(i, TITLES.length - 1)],
    t_sec: history.t_sec[idx],
  }));
}
