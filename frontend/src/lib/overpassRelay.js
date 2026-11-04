// The free relay: a Netlify function (frontend/netlify/functions/overpass.mjs) that asks the public Overpass servers from
// Netlify's own address, for the browser (same origin: no cross-origin refusal) and for the API (OVERPASS_RELAY_URL). Both
// the API's host and a visitor's network are sometimes refused by some servers; a third, different address often is not.
// Pure and tested here; the function file only wires Request/Response around it.

// Keep in step with ENDPOINTS of backend/services/overpass_svc.py: a backend test compares the two lists. A relay never
// forwards to a server a client names (that would make it an open proxy), only to these.
export const RELAY_MIRRORS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.openstreetmap.fr/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
  "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
];

export const MAX_QUERY_CHARS = 8000; // the queries of this application are ~600 characters
export const MAX_SERVER_TIMEOUT_S = 30;
export const RELAY_BUDGET_MS = 8500; // a Netlify function is cut at 10 s: answer (or fail) before that
export const RELAY_USER_AGENT = "PlantiersOutreachOS/1.0 (+https://plantiers.com; map relay)";

// Only the JSON queries this application builds: `[out:json][timeout:25]; …`. Never XML/CSV, never a long server timeout.
export function acceptableQuery(query) {
  if (typeof query !== "string" || !query.trim() || query.length > MAX_QUERY_CHARS) return false;
  const head = /^\s*\[out:json\](?:\[timeout:(\d{1,3})\])?\s*;/.exec(query);
  if (!head) return false;
  if (head[1] && Number(head[1]) > MAX_SERVER_TIMEOUT_S) return false;
  return !/\[out:(?!json)/.test(query);
}

// A browser sends `Origin`: a page of another site may not use this relay. No `Origin` = not a browser page (the API, curl).
export function originAllowed(origin, host) {
  if (!origin) return true;
  try { return new URL(origin).host === host; } catch { return false; }
}
