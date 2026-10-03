/* global AbortController */
// Overpass from the browser: the API host's address is often throttled by the public servers, a visitor's own connection is
// not. The server builds the query (and validates the area); the browser asks a public server; the answer goes back to the
// server's parser, so what is shown is still only what OpenStreetMap contributors published.
export const BROWSER_TIMEOUT_MS = 15000;

export async function fetchOverpass(query, endpoints, { fetchFn = (...a) => window.fetch(...a), timeoutMs = BROWSER_TIMEOUT_MS } = {}) {
  const failures = [];
  for (const endpoint of endpoints) {
    const host = new URL(endpoint).hostname;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const res = await fetchFn(endpoint, {
        method: "POST", body: new URLSearchParams({ data: query }), signal: ctl.signal,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (!res.ok) { failures.push(`${host}: HTTP ${res.status}`); continue; }
      const json = await res.json();
      if (json && Array.isArray(json.elements)) return json;
      failures.push(`${host}: not an Overpass answer`);
    } catch (e) {
      failures.push(`${host}: ${e && e.name === "AbortError" ? "timeout" : "unreachable"}`);
    } finally {
      clearTimeout(timer);
    }
  }
  const err = new Error(`Browser could not reach OpenStreetMap servers (${failures.join("; ")})`);
  err.failures = failures;
  throw err;
}
