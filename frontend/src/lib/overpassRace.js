/* global AbortController */
// A hedged race between public Overpass servers: the first one is asked at once, and a server that is merely slow gets the
// next one asked beside it (never more than `maxInFlight` at a time); the first valid answer wins and the others are aborted.
// A server that refuses us (403, 429, 5xx, unreachable) frees its place at once for the next one.
// Pure: no React, no window. The browser and the Netlify relay function share it, with their own `fetchFn`.
export const HEDGE_MS = 2500;
export const MAX_IN_FLIGHT = 3;

export function hostOf(endpoint) {
  if (String(endpoint).startsWith("/")) return "relay"; // this application's own relay, same origin
  try { return new URL(endpoint).hostname; } catch { return String(endpoint); }
}

export function raceOverpass(query, endpoints, {
  fetchFn, timeoutMs = 15000, hedgeMs = HEDGE_MS, maxInFlight = MAX_IN_FLIGHT, headers = {}, who = "Browser",
} = {}) {
  return new Promise((resolve, reject) => {
    const failures = new Array(endpoints.length).fill(null);
    const controllers = [];
    let next = 0;
    let inFlight = 0;
    let settled = false;
    let hedgeTimer = null;

    const finish = (done, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(hedgeTimer);
      controllers.forEach((c) => c.abort()); // the losers stop here, nobody waits for them
      done(value);
    };

    const launch = () => {
      clearTimeout(hedgeTimer);
      if (settled || next >= endpoints.length || inFlight >= maxInFlight) return;
      const index = next++;
      const endpoint = endpoints[index];
      const host = hostOf(endpoint);
      const ctl = new AbortController();
      controllers.push(ctl);
      const timer = setTimeout(() => ctl.abort(), timeoutMs);
      inFlight += 1;
      Promise.resolve()
        .then(() => fetchFn(endpoint, {
          method: "POST", body: new URLSearchParams({ data: query }), signal: ctl.signal,
          headers: { "Content-Type": "application/x-www-form-urlencoded", ...headers },
        }))
        .then(async (res) => {
          if (!res.ok) throw Object.assign(new Error("refused"), { label: `HTTP ${res.status}` });
          const json = await res.json();
          if (!(json && Array.isArray(json.elements))) throw Object.assign(new Error("bad"), { label: "not an Overpass answer" });
          if (typeof json.remark === "string" && json.remark.includes("runtime error")) {
            throw Object.assign(new Error("cut short"), { label: "query timed out on the server" });
          }
          return json;
        })
        .then(
          (json) => finish(resolve, json),
          (e) => { failures[index] = `${host}: ${e && e.label ? e.label : (e && e.name === "AbortError" ? "timeout" : "unreachable")}`; },
        )
        .then(() => {
          clearTimeout(timer);
          inFlight -= 1;
          if (settled) return;
          launch(); // a failure frees a place: the next server goes at once
          if (inFlight === 0 && next >= endpoints.length) {
            const list = failures.filter(Boolean);
            const err = new Error(`${who} could not reach OpenStreetMap servers (${list.join("; ")})`);
            err.failures = list;
            finish(reject, err);
          }
        });
      hedgeTimer = setTimeout(launch, hedgeMs); // still silent after hedgeMs: ask the next one beside it
    };

    if (!endpoints.length) {
      const err = new Error(`${who} could not reach OpenStreetMap servers (no server to ask)`);
      err.failures = [];
      reject(err);
      return;
    }
    launch();
  });
}
