// Pure helpers of the map search page: limits that mirror the API, counts, and the rows sent to the import.
import { siteState } from "@/lib/launchFormat";

export const MAX_LAT_SPAN = 0.2;
export const MAX_LON_SPAN = 0.3;
export const MAX_SITES_CHECKED = 25;
export const CATEGORY_LABELS = {
  restaurants: "Restaurants, cafés, bars",
  bakeries: "Bakeries, pastry",
  beauty: "Hairdressers, beauty",
  hotels: "Hotels, guest houses",
  shops: "Shops",
  crafts: "Crafts",
  offices: "Offices (law, accounting, real estate…)",
};

export const areaTooLarge = (b) => b.north - b.south > MAX_LAT_SPAN || b.east - b.west > MAX_LON_SPAN;

// What was really published, counted (never estimated): a missing value is "not published", not zero businesses.
export function summarize(places) {
  const count = (key) => places.filter((p) => p[key]).length;
  return { total: places.length, email: count("email"), phone: count("phone"), website: count("website") };
}

export function summaryText(places, truncated) {
  if (places.length === 0) return "No named place with published data in this area.";
  const s = summarize(places);
  const more = truncated ? " The area holds more places than the display limit: zoom in to see the rest." : "";
  return `${s.total} place${s.total === 1 ? "" : "s"}: ${s.email} with a published e-mail, ${s.phone} with a phone, ${s.website} with a website.${more}`;
}

// Rows for POST /prospect-imports (JSON): exactly the published fields, plus the position.
export const importRows = (places) =>
  places.map((p) => ({
    name: p.name, address: p.address, postcode: p.postcode, city: p.city, phone: p.phone, email: p.email,
    website: p.website, category: p.category, external_id: p.external_id, source_url: p.source_url, lat: p.lat, lon: p.lon,
  }));

export const IMPORT_ORIGIN = "OpenStreetMap contributors (ODbL), read live through the Overpass API from the map of this application";

export const markerColor = (p) => (p.email ? "#15803D" : p.phone || p.website ? "#B45309" : "#6B6B66");

// The organisation's own prospects on the map: colour = where they stand in the review, never a score.
export const STATUS_COLOR = { pending: "#2563EB", approved: "#15803D", rejected: "#991B1B" };
export const STATUS_LABEL = { pending: "to review", approved: "approved", rejected: "rejected" };

// The map draws only the prospects the server qualified (`map_ready`: e-mail, phone, address and position on a fresh source,
// a fit score; a website is never required). The page never recomputes that: the server decides before any limit.
export const readyOnly = (mine) => (mine || []).filter((p) => p.map_ready === true);

// "Hot" means an observed, sourced commercial intent and nothing else; a qualified prospect without one is not hot.
// "Hot" is an observed, sourced commercial intent decided by the server (`priority`), never a score: a high heat or fit
// score alone leaves a prospect "qualified" (docs/eligibility.md).
export const isHot = (p) => Boolean(p && p.priority === "hot");

// A place found by the search is drawn only when it published BOTH a phone and an e-mail: nothing else can be reached
// by a person. A missing value is unknown, never a default; the places left out are counted, not hidden silently.
export const reachablePlace = (p) => Boolean(p && p.phone && p.email);

export function readySummary(mine) {
  const ready = readyOnly(mine);
  if (ready.length === 0) {
    return "No qualified prospect on the map yet: the incomplete ones wait in Leads, to enrich.";
  }
  const plural = (n) => (n === 1 ? "" : "s");
  const hot = ready.filter(isHot).length;
  const sites = ready.filter((p) => p.has_website).length;
  const intent = hot > 0 ? `${hot} hot (observed intent)` : "none hot: no commercial intent observed";
  return `${ready.length} qualified prospect${plural(ready.length)} with e-mail, phone and address, ${sites} with a website, ${intent}.`;
}

// Room to keep free around the map for the floating panels, as Leaflet's [x, y] auto-pan paddings: a popup never opens under
// the search card (left) or the results drawer (right; at the bottom on a phone).
export function panelPadding({ narrow, open, hidden }) {
  if (hidden) return { topLeft: [20, 70], bottomRight: [20, 50] };
  if (narrow) return { topLeft: [20, open ? 360 : 70], bottomRight: [20, 50] };
  return { topLeft: [open ? 440 : 20, 70], bottomRight: [20, 50] };
}

// The perimeter a finished search really looked at: what the campaign takes as its zone. Null until a search succeeded.
export function zoneOf(job) {
  if (!job || job.status !== "succeeded") return null;
  const { south, west, north, east, category } = job;
  if ([south, west, north, east].some((v) => typeof v !== "number") || !category) return null;
  return { south, west, north, east, category };
}

const KM_PER_DEGREE = 111.32;

// "45.700–45.800° N · 4.780–4.900° E · ≈ 11 × 8 km · restaurants": numbers read from the search, nothing estimated beyond the size.
export function zoneSummary(zone) {
  if (!zone) return "";
  const height = (zone.north - zone.south) * KM_PER_DEGREE;
  const width = (zone.east - zone.west) * KM_PER_DEGREE * Math.cos((((zone.north + zone.south) / 2) * Math.PI) / 180);
  const f = (v) => v.toFixed(3);
  return `Périmètre recherché : ${f(zone.south)}–${f(zone.north)}° N · ${f(zone.west)}–${f(zone.east)}° E · ≈ ${Math.round(width)} × ${Math.round(height)} km · ${zone.category}`;
}

// The link to the campaign of this zone: the box and the category travel in the address, nothing is stored by the map.
export function journeyLink(zone, label) {
  const q = new URLSearchParams({ south: zone.south, west: zone.west, north: zone.north, east: zone.east, category: zone.category });
  if (label) q.set("label", label);
  return `/app/journey?${q.toString()}`;
}

// -------------------------------------------------------------
// What the map says about one of the organisation's prospects: only what the API returned, never a guess.
// -------------------------------------------------------------
// The tier is the server's decision (`priority`, `map_ready`/`eligible`): the page never re-ranks a prospect from its
// contacts or a score, and gives no "confidence" (the API provides none).
export const QUALIFICATION_TIERS = {
  HOT: {
    key: "HOT",
    label: "Hot — intention observée",
    color: "#F59E0B",
    glow: "0 0 16px rgba(245, 158, 11, 0.6)",
    bg: "rgba(245, 158, 11, 0.15)",
    border: "rgba(245, 158, 11, 0.4)",
  },
  QUALIFIED: {
    key: "QUALIFIED",
    label: "Qualifié prioritaire",
    color: "#7C3AED",
    glow: "0 0 14px rgba(124, 58, 237, 0.5)",
    bg: "rgba(124, 58, 237, 0.15)",
    border: "rgba(124, 58, 237, 0.4)",
  },
  NEEDS_REVIEW: {
    key: "NEEDS_REVIEW",
    label: "À compléter",
    color: "#94A3B8",
    glow: "none",
    bg: "rgba(148, 163, 184, 0.1)",
    border: "rgba(148, 163, 184, 0.3)",
  },
};

const detected = (p, key) => Array.isArray(p.signals) && p.signals.includes(key);

// The website as the server knows it, with the labels of the campaign screen (launchFormat.SITE_STATE_FR). An empty field is
// UNKNOWN: "no website identified" is said only when the server detected `no_website` (the listing was read and carried none).
export function mapSiteState(p) {
  if (!p) return "unknown";
  const known = p.has_website === true || Boolean(p.website && String(p.website).trim());
  if (known) return detected(p, "website_unreachable") ? "site_unreachable" : "site_found";
  if (detected(p, "no_website")) return "none_identified";
  return "unknown";
}

export function classifyProspect(p) {
  if (!p) {
    return { tier: "NEEDS_REVIEW", ...QUALIFICATION_TIERS.NEEDS_REVIEW, site: siteState("unknown"), siteKey: "unknown", reasons: [] };
  }
  const tierKey = isHot(p) ? "HOT" : p.map_ready === true || p.eligible === true ? "QUALIFIED" : "NEEDS_REVIEW";
  const tier = QUALIFICATION_TIERS[tierKey];
  const label = tierKey !== "NEEDS_REVIEW" && p.priority_label ? p.priority_label : tier.label;
  const siteKey = mapSiteState(p);
  const site = siteState(siteKey);

  // Facts carried by the response only: the server's priority, the review status, the site state and the signals it detected.
  const reasons = [];
  if (tierKey === "HOT") reasons.push("Intention commerciale observée et sourcée");
  if (tierKey === "QUALIFIED") reasons.push("E-mail, téléphone, adresse et position qualifiés par le serveur");
  if (p.review_status === "approved") reasons.push("Approuvé dans la revue");
  reasons.push(site.label);
  if (detected(p, "outdated_technology")) reasons.push("Marqueur technique ancien repéré sur la page d'accueil (heuristique)");

  return { tier: tierKey, ...tier, label, site, siteKey, reasons };
}
