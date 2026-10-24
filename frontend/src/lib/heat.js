// Lead heat as the API reports it: real information + score. Pure helpers, no invented figures.
export const TIER_LABEL = { hot: "Hot", warm: "Warm", cold: "Cold" };
export const FIELD_LABEL = {
  email: "e-mail", phone: "phone", website: "website", city: "city", company: "company", vertical: "category", country: "country", title: "job title",
};
export const TIERS = ["hot", "warm", "cold"];
export const TOP_FROM = 80; // the server's threshold (services/outreach_os/heat.py): the figure shown is `heat.top`, decided there

const names = (keys) => keys.map((k) => FIELD_LABEL[k] || k).join(", ");

// The tooltip / screen-reader sentence: what the figure is made of and what is missing.
export function heatTitle(heat) {
  if (!heat) return "Heat not available";
  const top = heat.top ? `TOP lead (heat ${TOP_FROM} or more): work it first. ` : "";
  const total = heat.known.length + heat.missing.length;
  const basis = heat.scored
    ? `score ${heat.score} and ${heat.known.length} of ${total} real fields known`
    : `not scored: ranked on the ${heat.known.length} of ${total} real fields known alone`;
  const known = heat.known.length ? ` Known: ${names(heat.known)}.` : "";
  const missing = heat.missing.length ? ` Missing: ${names(heat.missing)}.` : "";
  return `${top}${TIER_LABEL[heat.tier]} · heat ${heat.value}/100 (${basis}).${known}${missing}`;
}

// Lanes: every lead, the TOP ones (heat 80+), then one per tier.
export const LANES = ["all", "top", ...TIERS];
export const LANE_LABEL = { all: "All", top: "TOP", ...TIER_LABEL };

export function laneCounts(items) {
  const out = { top: 0, hot: 0, warm: 0, cold: 0, total: items.length };
  items.forEach((i) => {
    if (!i.heat) return;
    if (out[i.heat.tier] !== undefined) out[i.heat.tier] += 1;
    if (i.heat.top) out.top += 1;
  });
  return out;
}

export const inLane = (items, lane) => {
  if (lane === "all") return items;
  if (lane === "top") return items.filter((i) => i.heat && i.heat.top);
  return items.filter((i) => i.heat && i.heat.tier === lane);
};

// An empty lead has no e-mail, no phone and no website (the server says so in `heat.has_contact`): nothing to reach it with.
// Only an explicit `false` hides a lead; when the server did not say, the lead is shown rather than guessed away.
export const isEmpty = (item) => Boolean(item.heat) && item.heat.has_contact === false;
export const hasContact = (item) => !isEmpty(item);

// What a list shows: everything when `showEmpty`, otherwise only the leads that can be reached; `empty` is how many have none.
export function splitEmpty(items, showEmpty) {
  const empty = items.filter(isEmpty).length;
  return { shown: showEmpty ? items : items.filter(hasContact), empty };
}

export const EMPTY_RULE = "no e-mail, phone or website";
export const emptyNote = (n, showEmpty) =>
  n === 0 ? null : showEmpty ? `Showing ${n} empty lead${n === 1 ? "" : "s"} (${EMPTY_RULE}).` : `${n} empty lead${n === 1 ? "" : "s"} hidden (${EMPTY_RULE}).`;
