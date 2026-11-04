// "What to do next" as the API reports it: counted facts about the organisation's own leads. Pure helpers, no I/O.
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// "4 qualified prospects with e-mail, phone and address, 3 with a website": exactly the counts the server returned.
export function zoneLine(z) {
  const base = `${plural(z.ready, "qualified prospect", "qualified prospects")} with e-mail, phone and address`;
  return z.site > 0 ? `${base}, ${z.site} with a website` : base;
}

export const mapLink = (z) => `/app/map?city=${encodeURIComponent(z.city)}`;

// A prospect opens its review page; a CRM lead opens the CRM. The status says what a person still has to do.
export const leadLink = (l) => (l.kind === "prospect" ? `/app/prospects/${l.id}` : "/app/leads");

export function leadLine(l) {
  const place = [l.company && l.company !== l.name ? l.company : null, l.city].filter(Boolean).join(" · ");
  const status = l.review_status === "pending" ? "to review" : l.review_status === "approved" ? "approved" : null;
  return [place, status].filter(Boolean).join(" · ");
}

export const EMPTY_FOCUS =
  "Nothing to suggest yet: zones and contacts appear as soon as a prospect has an e-mail, a phone and an address on a fresh source. Enrich the incomplete ones to get there.";
