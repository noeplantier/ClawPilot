// Thin wrappers over /api/prospects and /api/outbound, plus the small hook the OutreachOS screens share.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/outreachFormat";

// The API enforces roles; the UI only hides what would be refused anyway.
export const canDecide = (user) => ["owner", "admin"].includes(user && user.role);

export const dashboardApi = {
  overview: () => api.get("/dashboard/overview").then((r) => r.data),
};

export const importsApi = {
  list: () => api.get("/prospect-imports").then((r) => r.data),
  submit: (body) => api.post("/prospect-imports", body).then((r) => r.data),
};

export const sourcesApi = {
  list: () => api.get("/sources").then((r) => r.data),
  discover: (body) => api.post("/sources/discover", body).then((r) => r.data),
  page: (runId, offset, limit) => api.get(`/sources/runs/${runId}`, { params: { offset, limit } }).then((r) => r.data),
  add: (runId, body) => api.post(`/sources/runs/${runId}/add`, body).then((r) => r.data),
};

export const mapApi = {
  // Searches are persisted jobs: start, poll, read the places. Nothing lives only in the browser.
  start: (area) => api.post("/map/search", area).then((r) => r.data),
  job: (id) => api.get(`/map/search/${id}`).then((r) => r.data),
  places: (id) => api.get(`/map/search/${id}/places`).then((r) => r.data),
  recent: (limit = 10) => api.get("/map/search", { params: { limit } }).then((r) => r.data),
  // Explicit fallback: the browser asked a public Overpass server itself because the server could not.
  ingest: (id, data) => api.post(`/map/search/${id}/ingest`, { data }).then((r) => r.data),
  prospects: () => api.get("/map/prospects").then((r) => r.data),
  // Where my leads are: hot / warm / cold counted per town (the dropdown of the town search).
  cities: () => api.get("/map/cities").then((r) => r.data),
  // One click on a pin: the place becomes a prospect (and, by the person's choice, joins the CRM).
  addPlace: (body) => api.post("/map/places/add", body).then((r) => r.data),
};

export const focusApi = {
  // Where to prospect next and who to contact first, counted by the server from the organisation's own leads.
  get: () => api.get("/suggestions/focus").then((r) => r.data),
};

export const campaignsApi = {
  create: (body) => api.post("/campaigns", body).then((r) => r.data),
  assign: (id, leadIds) => api.post(`/campaigns/${id}/assign-leads`, { lead_ids: leadIds }).then((r) => r.data),
};

export const systemApi = {
  health: () => api.get("/system/health").then((r) => r.data),
  probeOverpass: () => api.post("/system/health/overpass").then((r) => r.data),
};

export const prospectsApi = {
  list: (params) => api.get("/prospects", { params }).then((r) => r.data),
  // `hideEmpty`: leave out the leads with no e-mail, phone or website (the answer still says how many there are: `empty`).
  queues: (status = "pending", { hideEmpty = false } = {}) =>
    api.get("/prospects/queues", { params: { review_status: status, ...(hideEmpty ? { hide_empty: true } : {}) } }).then((r) => r.data),
  get: (id) => api.get(`/prospects/${id}`).then((r) => r.data),
  events: (id) => api.get(`/prospects/${id}/events`).then((r) => r.data),
  review: (id, decision, note) => api.post(`/prospects/${id}/review`, { decision, note: note || null }).then((r) => r.data),
  rescore: (id) => api.post(`/prospects/${id}/rescore`).then((r) => r.data),
  dismissSignal: (id, key, reason) => api.post(`/prospects/${id}/signals/${key}/dismiss`, { reason }).then((r) => r.data),
  restoreSignal: (id, key) => api.post(`/prospects/${id}/signals/${key}/restore`).then((r) => r.data),
  erase: (id) => api.post(`/prospects/${id}/erase`),
  runDiscovery: () => api.post("/prospects/discovery/run", { source: "fixture_directory" }).then((r) => r.data),
  createDraft: (id) => api.post(`/prospects/${id}/drafts`).then((r) => r.data),
  // Subject and message only: the footer (coordinates, data origin, unsubscribe link) is rebuilt by the server.
  editDraft: (draftId, body) => api.patch(`/prospects/drafts/${draftId}`, body).then((r) => r.data),
  reviewDraft: (draftId, decision) => api.post(`/prospects/drafts/${draftId}/review`, { decision }).then((r) => r.data),
  settings: () => api.get("/prospects/settings").then((r) => r.data),
};

export const outboundApi = {
  status: () => api.get("/outbound/status").then((r) => r.data),
  limits: () => api.get("/outbound/limits").then((r) => r.data),
  putLimits: (patch) => api.put("/outbound/limits", patch).then((r) => r.data),
  list: (params) => api.get("/outbound", { params }).then((r) => r.data),
  get: (id) => api.get(`/outbound/${id}`).then((r) => r.data),
  dispatch: (draftId) => api.post("/outbound/dispatch", { draft_id: draftId }).then((r) => r.data),
  syncInbox: () => api.post("/outbound/sync-inbox").then((r) => r.data),
  testSend: (to) => api.post("/outbound/test-send", { to }).then((r) => r.data),
  testWhatsapp: (to) => api.post("/outbound/test-whatsapp", { to }).then((r) => r.data),
  simulate: (id, event, text) => api.post(`/outbound/${id}/simulate`, { event, text: text || null }).then((r) => r.data),
};

// useAsync(fn, deps) -> { data, error, loading, reload }. `error` is already a readable sentence.
// A stale response (older request finishing late, or an unmounted screen) is ignored.
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const ticket = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);
  const reload = useCallback(async () => {
    const mine = ++ticket.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await run();
      if (mine === ticket.current) setState({ data, error: null, loading: false });
    } catch (e) {
      if (mine === ticket.current) setState({ data: null, error: describeApiError(e), loading: false });
    }
  }, [run]);
  useEffect(() => {
    reload();
    return () => {
      ticket.current += 1;
    };
  }, [reload]);
  return { ...state, reload };
}
