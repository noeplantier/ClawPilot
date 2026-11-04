// Free Overpass relay on Netlify (reached at /relay/overpass, see netlify.toml). Same contract as an Overpass server:
// POST a form with `data=<query>`, get the Overpass JSON back. The logic is in src/lib (tested); this file wires it.
import { raceOverpass } from "../../src/lib/overpassRace.js";
import {
  RELAY_MIRRORS, RELAY_BUDGET_MS, RELAY_USER_AGENT, acceptableQuery, originAllowed,
} from "../../src/lib/overpassRelay.js";

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
});

export default async (req) => {
  if (req.method !== "POST") return json({ error: "POST a form with data=<Overpass query>" }, 405);
  if (!originAllowed(req.headers.get("origin"), new URL(req.url).host)) return json({ error: "cross-origin use refused" }, 403);
  let query = "";
  try { query = String((await req.formData()).get("data") || ""); } catch (e) { return json({ error: "expected a form" }, 400); }
  if (!acceptableQuery(query)) return json({ error: "only the JSON queries of this application are relayed" }, 400);
  try {
    const answer = await raceOverpass(query, RELAY_MIRRORS, {
      fetchFn: (url, init) => fetch(url, init),
      timeoutMs: RELAY_BUDGET_MS, hedgeMs: 2000, maxInFlight: 3, headers: { "User-Agent": RELAY_USER_AGENT, Accept: "application/json" },
      who: "Relay",
    });
    return json(answer);
  } catch (e) {
    return json({ error: String((e && e.message) || "relay failed"), failures: (e && e.failures) || [] }, 502);
  }
};
