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
