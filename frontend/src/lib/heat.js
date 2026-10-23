// Lead heat as the API reports it: real information + score. Pure helpers, no invented figures.
export const TIER_LABEL = { hot: "Hot", warm: "Warm", cold: "Cold" };
export const FIELD_LABEL = {
  email: "e-mail", phone: "phone", website: "website", city: "city", company: "company", vertical: "category", country: "country", title: "job title",
};
export const TIERS = ["hot", "warm", "cold"];

const names = (keys) => keys.map((k) => FIELD_LABEL[k] || k).join(", ");

// The tooltip / screen-reader sentence: what the figure is made of and what is missing.
export function heatTitle(heat) {
  if (!heat) return "Heat not available";
  const total = heat.known.length + heat.missing.length;
  const basis = heat.scored
    ? `score ${heat.score} and ${heat.known.length} of ${total} real fields known`
    : `not scored: ranked on the ${heat.known.length} of ${total} real fields known alone`;
  const known = heat.known.length ? ` Known: ${names(heat.known)}.` : "";
  const missing = heat.missing.length ? ` Missing: ${names(heat.missing)}.` : "";
  return `${TIER_LABEL[heat.tier]} · heat ${heat.value}/100 (${basis}).${known}${missing}`;
}

export function laneCounts(items) {
  const out = { hot: 0, warm: 0, cold: 0, total: items.length };
  items.forEach((i) => { if (i.heat && out[i.heat.tier] !== undefined) out[i.heat.tier] += 1; });
  return out;
}

export const inLane = (items, lane) => (lane === "all" ? items : items.filter((i) => i.heat && i.heat.tier === lane));
