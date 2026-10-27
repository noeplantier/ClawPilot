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

// Source ids already imported: the search must not offer them a second time.
export const knownIds = (mine) => new Set(mine.map((p) => p.external_id).filter(Boolean));

// The map shows only the leads the server marked `map_ready`: hot, with a phone and an e-mail really known. The page never
// recomputes that; the other prospects stay in the data so a place already imported is not offered a second time.
export const readyOnly = (mine) => mine.filter((p) => p.map_ready === true);

// A place found by the search is drawn only when it published BOTH a phone and an e-mail: nothing else can be reached
// by a person. A missing value is unknown, never a default; the places left out are counted, not hidden silently.
export const reachablePlace = (p) => Boolean(p && p.phone && p.email);

export function readySummary(mine) {
  if (mine.length === 0) return "No prospect with a position yet.";
  const ready = readyOnly(mine);
  const plural = (n) => (n === 1 ? "" : "s");
  if (ready.length === 0) {
    return `No hot lead with a phone and an e-mail yet (${mine.length} prospect${plural(mine.length)} with a position, not hot or missing a phone or an e-mail).`;
  }
  const sites = ready.filter((p) => p.has_website).length;
  return `${ready.length} hot lead${plural(ready.length)} with a phone and an e-mail, ${sites} with a website.`;
}

// Room to keep free around the map for the floating panels, as Leaflet's [x, y] auto-pan paddings: a popup never opens under
// the search card (left) or the results drawer (right; at the bottom on a phone).
export function panelPadding({ narrow, searchOpen, panelOpen, hidden }) {
  if (hidden) return { topLeft: [20, 70], bottomRight: [20, 50] };
  if (narrow) return { topLeft: [20, searchOpen ? 360 : 70], bottomRight: [20, panelOpen ? 280 : 50] };
  return { topLeft: [searchOpen ? 440 : 20, 70], bottomRight: [panelOpen ? 400 : 20, 50] };
}
