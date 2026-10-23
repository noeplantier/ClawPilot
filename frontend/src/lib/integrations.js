/* global AbortController */
// Pure helpers for Settings > Integrations. The server computes every status (GET /settings/integrations); a live test only
// refines it for the session. Nothing here invents a status: no result means the server's status stands.

export const GROUPS = [
  ["data", "Data & hosting"],
  ["sources", "Prospect sources"],
  ["sending", "Sending"],
  ["inbound", "Inbound webhooks"],
  ["ai", "AI composer"],
];

// tone → chip class and sort weight (what needs attention first within a group)
export const TONE = {
  ready: { chip: "chip-success", rank: 5 },
  unchecked: { chip: "chip-cyan", rank: 4 },
  off: { chip: "chip-ink", rank: 3 },
  partial: { chip: "chip-warn", rank: 2 },
  missing: { chip: "chip-warn", rank: 1 },
  blocked: { chip: "chip-danger", rank: 0 },
};

// A failed live test: services the product can work without (it has a fallback) become "partial", the rest "blocked".
const SOFT_FAIL = new Set(["osm", "geocoder", "registry"]);

export function groupItems(items) {
  const byGroup = new Map(GROUPS.map(([key]) => [key, []]));
  for (const item of items || []) (byGroup.get(item.group) || byGroup.set(item.group, []).get(item.group)).push(item);
  return GROUPS.map(([key, label]) => [key, label, byGroup.get(key)]).filter(([, , list]) => list.length > 0);
}

// The status shown for an entry: the server's, refined by this session's test when there is one.
export function effective(item, result) {
  if (!result || result.outcome === "skipped" || result.outcome === "error") return { status: item.status, label: item.label };
  if (result.outcome === "passed") {
    const ms = result.latency_ms != null ? ` · ${result.latency_ms} ms` : "";
    return { status: "ready", label: `VERIFIED${ms}` };
  }
  return { status: SOFT_FAIL.has(item.id) ? "partial" : "blocked", label: "TEST FAILED" };
}

export function summarize(items, results = {}) {
  const counts = { ready: 0, unchecked: 0, off: 0, partial: 0, missing: 0, blocked: 0 };
  for (const item of items || []) counts[effective(item, results[item.id]).status] += 1;
  const attention = counts.partial + counts.missing + counts.blocked;
  return { ...counts, attention, total: (items || []).length };
}

export function testable(items) {
  return (items || []).filter((i) => i.test);
}

// What to paste into the hosting dashboard: names only, one per line. Values are typed by the owner there, never here.
export function needsList(item) {
  return (item.needs || []).join("\n");
}

export const GEOCODER_URL = "https://api-adresse.data.gouv.fr/search/?q=Lyon&type=municipality&limit=1";

// The city search is called from the browser, so the browser is what gets tested. `fetchImpl` is injectable for tests.
export async function testGeocoder(fetchImpl = fetch, { timeoutMs = 8000, now = () => Date.now() } = {}) {
  const started = now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(GEOCODER_URL, { signal: controller.signal });
    const latency = now() - started;
    if (!response.ok) return { ok: false, outcome: "failed", latency_ms: latency, detail: `The city search answered HTTP ${response.status}.` };
    const body = await response.json();
    const found = Array.isArray(body?.features) && body.features.length > 0;
    return found
      ? { ok: true, outcome: "passed", latency_ms: latency, detail: "The city search answered from your browser." }
      : { ok: false, outcome: "failed", latency_ms: latency, detail: "The city search answered without a result for a known city." };
  } catch (e) {
    const reason = e && e.name === "AbortError" ? `no answer within ${Math.round(timeoutMs / 1000)} s` : "the request was blocked or the network is down";
    return { ok: false, outcome: "failed", latency_ms: null, detail: `The city search is unreachable from your browser: ${reason}.` };
  } finally {
    clearTimeout(timer);
  }
}
