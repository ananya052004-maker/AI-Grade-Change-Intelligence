const BASE = "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get("/api/health"),
  listTransitions: () => get("/api/transitions"),
  getTransition: (id: string) => get(`/api/transitions/${id}`),
  tick: (id: string, tSec: number) => get(`/api/transitions/${id}/tick?t_sec=${tSec}`),
  history: (id: string) => get(`/api/transitions/${id}/history`),
  timeline: (id: string) => get(`/api/transitions/${id}/timeline`),
  whatif: (id: string, tSec: number, overrides: Record<string, number>) =>
    post(`/api/transitions/${id}/whatif`, { t_sec: tSec, overrides }),
  dropTag: (id: string, tag: string) => post(`/api/transitions/${id}/drop_tag/${tag}`, {}),
  restoreTag: (id: string, tag: string) => post(`/api/transitions/${id}/restore_tag/${tag}`, {}),
  correlations: () => get("/api/correlations"),
  stabilizationImpact: () => get("/api/correlations/stabilization-impact"),
  submitFeedback: (body: { suggestion_id: string; response: string; operator_id: string; reject_reason?: string }) =>
    post("/api/feedback", body),
  feedbackQuality: () => get("/api/feedback/quality"),
  feedbackLog: () => get("/api/feedback/log?limit=50"),
  wsUrl: (id: string, speed = 20) => `ws://localhost:8000/ws/transitions/${id}?speed=${speed}`,
};
