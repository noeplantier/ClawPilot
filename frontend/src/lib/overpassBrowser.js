// Overpass from the browser: the API host's address is often throttled or refused by the public servers, a visitor's own
// connection is not. The server builds the query (and validates the area); the browser asks the public servers; the answer goes
// back to the server's parser, so what is shown is still only what OpenStreetMap contributors published.
//
// The servers are raced, not tried one after the other: this application's own relay (same origin, so no cross-origin refusal)
// goes first, a slow server is hedged by the next one after 2.5 s, and the first valid answer wins.
import { raceOverpass } from "@/lib/overpassRace";

export const BROWSER_TIMEOUT_MS = 15000;
export const RELAY_PATH = "/relay/overpass"; // Netlify function of this application: frontend/netlify/functions/overpass.mjs

export function fetchOverpass(query, endpoints, {
  fetchFn = (...a) => window.fetch(...a), timeoutMs = BROWSER_TIMEOUT_MS, hedgeMs, relay = false,
} = {}) {
  const servers = relay ? [RELAY_PATH, ...endpoints.filter((e) => e !== RELAY_PATH)] : endpoints;
  return raceOverpass(query, servers, { fetchFn, timeoutMs, hedgeMs, who: "Browser" });
}
