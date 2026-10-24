// Pure helpers of the map's town search: URLs, parsing, matching and ranking of the suggestions. No DOM, no network.
//
// Two free public services of the French government answer from the browser, with no key: the communes API (geo.api.gouv.fr,
// the official list, ranked by population) and the address API (api-adresse.data.gouv.fr) as a fallback. Only the typed text leaves
// the browser. The counts of leads per town come from this server (GET /map/cities) and are shown as they are: a town the
// organisation has no lead in says so, and while the counts are not loaded nothing is shown (never a made-up 0).

export const COMMUNES_URL = "https://geo.api.gouv.fr/communes";
export const ADDRESS_URL = "https://api-adresse.data.gouv.fr/search/";
export const MIN_CHARS = 2;
export const MAX_SUGGESTIONS = 8;
const FIELDS = "nom,code,codesPostaux,centre,population,departement";
const SAINT = { st: "saint", ste: "sainte" };

// Same key as the server (services/outreach_os/cities.py): `Saint-Étienne`, `st etienne` and `SAINT ETIENNE` are one town.
export function fold(name) {
  const plain = String(name || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  return plain.split(/[^a-z0-9]+/).filter(Boolean).map((w) => SAINT[w] || w).join(" ");
}

// `St-Etienne` is `Saint-Etienne` once the word is finished; while it is the last word being typed (`st`) it may still become
// `Strasbourg`, so both readings are tried (see `forms`).
export const expandSaint = (text) => String(text || "").replace(/(^|[^\p{L}])(ste?)(?=[\s\-'\u2019])/giu, (m, pre, w) => `${pre}${SAINT[w.toLowerCase()]}`);

export function forms(query) {
  const words = String(query || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  const finished = words.map((w, i) => (i < words.length - 1 ? SAINT[w] || w : w)).join(" "); // the last word may still be growing
  const abbreviated = words.map((w) => SAINT[w] || w).join(" ");
  return [...new Set([finished, abbreviated])].filter(Boolean);
}

export const isPostcode = (q) => /^\d{5}$/.test(String(q || "").trim());

export function communesUrl(q) {
  const text = String(q || "").trim();
  return isPostcode(text)
    ? `${COMMUNES_URL}?codePostal=${text}&fields=${FIELDS}&limit=${MAX_SUGGESTIONS}`
    : `${COMMUNES_URL}?nom=${encodeURIComponent(expandSaint(text))}&fields=${FIELDS}&boost=population&limit=${MAX_SUGGESTIONS}`;
}

export const addressUrl = (q) => `${ADDRESS_URL}?q=${encodeURIComponent(expandSaint(String(q || "").trim()))}&type=municipality&limit=${MAX_SUGGESTIONS}`;

const finite = (n) => typeof n === "number" && Number.isFinite(n);

// A suggestion: { id, name, label, detail, lat, lon, population, counts, local }. `counts` is attached later, by `suggest`.
export function parseCommunes(json) {
  if (!Array.isArray(json)) return [];
  return json
    .map((c) => {
      const [lon, lat] = (c && c.centre && c.centre.coordinates) || [];
      if (!c || !c.nom || !finite(lat) || !finite(lon)) return null;
      const codes = Array.isArray(c.codesPostaux) ? c.codesPostaux : [];
      const dept = (c.departement && c.departement.code) || c.codeDepartement;
      const postcode = codes.length === 1 ? codes[0] : null;
      return {
        id: `c:${c.code || c.nom}`, name: c.nom, lat, lon, population: finite(c.population) ? c.population : null, local: false,
        label: postcode ? `${c.nom} (${postcode})` : dept ? `${c.nom} (${dept})` : c.nom,
        detail: [c.departement && c.departement.nom, codes.length > 1 ? `${codes[0]}–${codes[codes.length - 1]}` : null].filter(Boolean).join(" · "),
      };
    })
    .filter(Boolean);
}

export function parseAddress(json) {
  const features = json && Array.isArray(json.features) ? json.features : [];
  return features
    .map((f) => {
      const p = f && f.properties;
      const [lon, lat] = (f && f.geometry && f.geometry.coordinates) || [];
      if (!p || !p.city || !finite(lat) || !finite(lon)) return null;
      return {
        id: `a:${p.citycode || p.city}:${p.postcode || ""}`, name: p.city, lat, lon, population: null, local: false,
        label: p.postcode ? `${p.city} (${p.postcode})` : p.city, detail: p.context || "",
      };
    })
    .filter(Boolean);
}

// 0 = the typed text is the whole name, 1 = the name (or one of its words) starts with it, 2 = it is inside the name, null = no match.
export function matchClass(query, name) {
  const n = fold(name);
  if (!n) return null;
  let best = null;
  for (const q of forms(query)) {
    let cls = null;
    if (n === q) cls = 0;
    else if (n.startsWith(q) || n.split(" ").some((w, i, all) => all.slice(i).join(" ").startsWith(q))) cls = 1;
    else if (n.includes(q)) cls = 2;
    if (cls !== null && (best === null || cls < best)) best = cls;
  }
  return best;
}

// Mean position of the organisation's own prospects, per town: lets a town known only from the leads be reached without a lookup.
export function centroids(points) {
  const sums = new Map();
  for (const p of points || []) {
    const key = fold(p.city);
    if (!key || !finite(p.lat) || !finite(p.lon)) continue;
    const s = sums.get(key) || { lat: 0, lon: 0, n: 0 };
    sums.set(key, { lat: s.lat + p.lat, lon: s.lon + p.lon, n: s.n + 1 });
  }
  return new Map([...sums].map(([k, s]) => [k, { lat: s.lat / s.n, lon: s.lon / s.n }]));
}

const countsOf = (stat) => (stat ? { hot: stat.hot, warm: stat.warm, cold: stat.cold, total: stat.total } : { hot: 0, warm: 0, cold: 0, total: 0 });

// The suggestions for what is typed. `remote` answers `remoteFor` (a folded query); when the person has typed more since, only the
// entries that still match are kept, so the list narrows at once instead of vanishing while the next answer is on its way.
// `stats` is the server's per-town counts (null until loaded). The leads of a town are attached to the most populous commune of that
// name: a lead carries the name of its town, not its postcode.
export function suggest(query, { remote = [], remoteFor = "", stats = null, positions = new Map(), limit = MAX_SUGGESTIONS } = {}) {
  const q = fold(query);
  if (q.length < MIN_CHARS) return [];
  const fresh = remoteFor === q;
  const byKey = new Map((stats || []).map((s) => [s.key, s]));
  const seen = new Set();
  const out = [];
  remote.forEach((r, order) => {
    const cls = matchClass(q, r.name);
    if (!fresh && cls === null) return;
    const key = fold(r.name);
    const first = !seen.has(key);
    seen.add(key);
    out.push({ ...r, cls: cls === null ? 3 : cls, order, counts: stats ? (first ? countsOf(byKey.get(key)) : null) : null });
  });
  // a town of the leads that the commune list did not return (a misspelling, an unknown commune) is still offered
  (stats || []).forEach((s, i) => {
    const cls = matchClass(q, s.city);
    if (cls === null || seen.has(s.key)) return;
    const at = positions.get(s.key);
    out.push({ id: `l:${s.key}`, name: s.city, label: s.city, detail: "from your leads", lat: at ? at.lat : null, lon: at ? at.lon : null, population: null, local: true, cls, order: 1000 + i, counts: countsOf(s) });
  });
  const hot = (e) => (e.counts ? e.counts.hot : 0);
  return out.sort((a, b) => a.cls - b.cls || hot(b) - hot(a) || a.order - b.order).slice(0, limit);
}

// The towns shown before anything is typed: where the hot leads are, reachable at once when my prospects there have a position.
export function hottest(stats, limit = 6, positions = new Map()) {
  return (stats || [])
    .filter((s) => s.total > 0)
    .slice(0, limit)
    .map((s) => {
      const at = positions.get(s.key);
      return { id: `l:${s.key}`, name: s.city, label: s.city, detail: "from your leads", lat: at ? at.lat : null, lon: at ? at.lon : null, population: null, local: true, cls: 0, order: 0, counts: countsOf(s) };
    });
}

// What the badge says next to a suggestion. null = nothing known (the counts did not load): nothing is shown rather than a 0.
export function countsText(counts) {
  if (!counts) return null;
  if (counts.total === 0) return "no lead yet";
  return `${counts.hot} hot · ${counts.total} lead${counts.total === 1 ? "" : "s"}`;
}

// How close to fly: a big city needs a wider view than a village, but never wider than the search accepts.
export const zoomFor = (population) => (population !== null && population !== undefined && population < 3000 ? 15 : 14);
