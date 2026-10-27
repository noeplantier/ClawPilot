// The screens of the app, loaded on demand (one chunk each) and warmed up before they are asked for, so that opening one is
// instant: the nav link warms its screen on hover or focus, and every screen is fetched once the browser is idle after the first paint.
export const pages = {
  dashboard: () => import("@/pages/Dashboard"),
  campaigns: () => import("@/pages/Campaigns"),
  leads: () => import("@/pages/Leads"),
  agents: () => import("@/pages/Agents"),
  messages: () => import("@/pages/Messages"),
  analytics: () => import("@/pages/Analytics"),
  settings: () => import("@/pages/Settings"),
  prospects: () => import("@/pages/Prospects"),
  map: () => import("@/pages/MapSearch"),
  sources: () => import("@/pages/Sources"),
  system: () => import("@/pages/SystemHealth"),
  prospectDetail: () => import("@/pages/ProspectDetail"),
  review: () => import("@/pages/ReviewQueue"),
  sending: () => import("@/pages/Sending"),
  prospectImport: () => import("@/pages/ProspectImport"),
};

// The screen behind an in-app path (`/app/leads?view=kanban` -> leads); null for a path that has none.
const BY_PATH = {
  "/app/dashboard": "dashboard", "/app/campaigns": "campaigns", "/app/leads": "leads", "/app/agents": "agents",
  "/app/messages": "messages", "/app/analytics": "analytics", "/app/settings": "settings", "/app/prospects": "prospects",
  "/app/map": "map", "/app/sources": "sources", "/app/system": "system", "/app/prospects/review": "review",
  "/app/sending": "sending", "/app/prospects/import": "prospectImport",
};
export const pageOf = (to) => BY_PATH[String(to || "").split("?")[0].replace(/\/$/, "")] || null;

const asked = new Set();

// Start loading one screen; harmless to call again, and a failure (offline) is not an error: the real navigation retries.
export function prefetch(name) {
  if (!name || asked.has(name) || !pages[name]) return;
  asked.add(name);
  pages[name]().catch(() => asked.delete(name));
}

export const prefetchPath = (to) => prefetch(pageOf(to));

// Every screen, once the browser has nothing better to do. A visitor who asked to save data keeps the on-demand loading only.
export function prefetchAll() {
  const connection = typeof navigator !== "undefined" ? navigator.connection : null;
  if (connection && connection.saveData) return;
  Object.keys(pages).forEach(prefetch);
}

export function whenIdle(fn) {
  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") window.requestIdleCallback(fn, { timeout: 4000 });
  else setTimeout(fn, 1500);
}
