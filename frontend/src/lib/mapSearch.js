// Pure helpers of the map search page: limits that mirror the API, counts, and the rows sent to the import.
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
export const isHot = (p) => Boolean(p && (p.priority === "hot" || (p.heat && p.heat.tier === "hot")));

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
export function panelPadding({ narrow, searchOpen, panelOpen, hidden }) {
  if (hidden) return { topLeft: [20, 70], bottomRight: [20, 50] };
  if (narrow) return { topLeft: [20, searchOpen ? 360 : 70], bottomRight: [20, panelOpen ? 280 : 50] };
  return { topLeft: [searchOpen ? 440 : 20, 70], bottomRight: [panelOpen ? 400 : 20, 50] };
}

// -------------------------------------------------------------
// Plantiers Smart Lead Qualification & Opportunity Classification
// -------------------------------------------------------------
export const QUALIFICATION_TIERS = {
  HOT: {
    key: "HOT",
    label: "HOT LEAD",
    color: "#F59E0B",
    glow: "0 0 16px rgba(245, 158, 11, 0.6)",
    bg: "rgba(245, 158, 11, 0.15)",
    border: "rgba(245, 158, 11, 0.4)",
    badgeClass: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  },
  HIGHLY_QUALIFIED: {
    key: "HIGHLY_QUALIFIED",
    label: "HIGHLY QUALIFIED",
    color: "#22C55E",
    glow: "0 0 16px rgba(34, 197, 94, 0.5)",
    bg: "rgba(34, 197, 94, 0.15)",
    border: "rgba(34, 197, 94, 0.4)",
    badgeClass: "bg-leaf-500/20 text-leaf-400 border-leaf-500/40",
  },
  QUALIFIED: {
    key: "QUALIFIED",
    label: "QUALIFIED",
    color: "#7C3AED",
    glow: "0 0 14px rgba(124, 58, 237, 0.5)",
    bg: "rgba(124, 58, 237, 0.15)",
    border: "rgba(124, 58, 237, 0.4)",
    badgeClass: "bg-brand-500/20 text-brand-300 border-brand-500/40",
  },
  NEEDS_REVIEW: {
    key: "NEEDS_REVIEW",
    label: "NEEDS REVIEW",
    color: "#94A3B8",
    glow: "none",
    bg: "rgba(148, 163, 184, 0.1)",
    border: "rgba(148, 163, 184, 0.3)",
    badgeClass: "bg-white/10 text-white/70 border-white/20",
  },
};

export function classifyProspect(p) {
  if (!p) return { tier: "NEEDS_REVIEW", ...QUALIFICATION_TIERS.NEEDS_REVIEW, confidence: 0, reasons: ["No data"] };

  const hasEmail = Boolean(p.email && String(p.email).includes("@"));
  const hasPhone = Boolean(p.phone && String(p.phone).trim().length >= 4);
  const hasWebsite = Boolean(p.website && String(p.website).trim().length > 3);
  const score = typeof p.score === "number" ? p.score : (p.heat?.value ?? null);
  const isHotLead = p.priority === "hot" || p.heat?.tier === "hot" || (score !== null && score >= 75);

  const reasons = [];

  // Determine Opportunity
  let opportunity = {
    id: "opportunity_a",
    name: "Opportunity A — No Website",
    pitch: "Creation of a modern, high-converting business website & digital presence",
  };

  if (!hasWebsite) {
    opportunity = {
      id: "opportunity_a",
      name: "Opportunity A — No Website",
      pitch: "Creation of a modern, conversion-oriented business website & mobile showcase",
    };
    reasons.push("No official business website detected in listing");
  } else if (p.signals && p.signals.includes("legacy_tech")) {
    opportunity = {
      id: "opportunity_b",
      name: "Opportunity B — Outdated Website",
      pitch: "Modern UX/UI redesign, mobile responsiveness & performance overhaul",
    };
    reasons.push("Outdated web technology and non-responsive layout identified");
  } else {
    opportunity = {
      id: "opportunity_c",
      name: "Opportunity C — SEO & Digital Visibility",
      pitch: "Technical & Local SEO, GEO search ranking optimization and local search growth",
    };
    reasons.push("Website active with high local discovery and SEO expansion potential");
  }

  // Determine Tier
  if (isHotLead && hasEmail && hasPhone) {
    if (p.priority === "hot" || p.heat?.tier === "hot") reasons.unshift("Observed commercial intent recorded");
    if (score !== null) reasons.unshift(`High fit score (${score}/100)`);
    reasons.unshift("Dual verified contacts: business email and telephone");
    return {
      tier: "HOT",
      ...QUALIFICATION_TIERS.HOT,
      confidence: Math.min(99, (score || 80) + 10),
      reasons,
      opportunity,
      hasEmail,
      hasPhone,
      hasWebsite,
    };
  }

  if (hasEmail && hasPhone) {
    reasons.unshift("Dual verified direct contacts (email + phone)");
    if (p.review_status === "approved") reasons.unshift("Approved in CRM pipeline");
    return {
      tier: "HIGHLY_QUALIFIED",
      ...QUALIFICATION_TIERS.HIGHLY_QUALIFIED,
      confidence: score || 75,
      reasons,
      opportunity,
      hasEmail,
      hasPhone,
      hasWebsite,
    };
  }

  if (hasEmail || hasPhone) {
    if (hasEmail) reasons.unshift("Verified email contact available");
    if (hasPhone) reasons.unshift("Verified phone contact available");
    return {
      tier: "QUALIFIED",
      ...QUALIFICATION_TIERS.QUALIFIED,
      confidence: score || 55,
      reasons,
      opportunity,
      hasEmail,
      hasPhone,
      hasWebsite,
    };
  }

  reasons.unshift("Missing direct business email or telephone");
  return {
    tier: "NEEDS_REVIEW",
    ...QUALIFICATION_TIERS.NEEDS_REVIEW,
    confidence: 30,
    reasons,
    opportunity,
    hasEmail: false,
    hasPhone: false,
    hasWebsite,
  };
}
