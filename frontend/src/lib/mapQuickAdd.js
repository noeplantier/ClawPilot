// One click on a map point: the request body, and a plain-language account of what the server really did.
// Nothing is guessed here: every line comes from the answer of POST /map/places/add.

export const ATTEST_PREF = "map.attested";
export const ATTEST_TEXT =
  "I confirm that I may use these professional contact details for B2B prospecting (legitimate interest), and that I will honour opt-outs.";

const FIELDS = ["external_id", "name", "lat", "lon", "category", "address", "postcode", "city", "phone", "email", "website", "source_url"];

// Only what the map published goes back to the server (which re-validates it); an empty value is left out, never invented.
export function quickAddBody(place, { approve = true, checkWebsite = true } = {}) {
  const row = {};
  for (const key of FIELDS) {
    const value = place[key];
    if (value !== null && value !== undefined && value !== "") row[key] = value;
  }
  return { place: row, attestation: true, approve, check_website: Boolean(checkWebsite && place.website) };
}

// The lines shown after an addition. `asked` says whether the website was to be read, so "not read" is never shown as "no e-mail".
export function describeAdded(out, { siteAsked = false } = {}) {
  const lines = [];
  lines.push(out.created ? `${out.name} is added.` : `${out.name} was already one of your prospects: its details are completed, nothing is duplicated.`);
  lines.push(out.in_crm ? "It is in your CRM (approved by you). Nothing was sent." : "It waits in the review queue. Nothing was sent.");
  if (out.email) lines.push(`E-mail: ${out.email}${out.email_found_on_site ? " (found on its own website)" : " (published on the map)"}.`);
  else lines.push("E-mail: not known.");
  lines.push(out.phone ? `Phone: ${out.phone}.` : "Phone: not known.");
  // The map draws only qualified prospects: say where this one stands instead of letting it vanish.
  if (!out.email || !out.phone) lines.push("Not on the map yet: it needs an e-mail, a phone and an address. It waits in Prospects > To enrich.");
  if (siteAsked) {
    lines.push(out.website_checked ? "Its website was read." : "Its website could not be read (blocked by its robots.txt, unreachable, or over the limit): that says nothing about its e-mail.");
  }
  return lines;
}

// ---- One click on the whole selection (POST /map/places/add-many) ----
export const MAX_PER_REQUEST = 200; // the server's limit per call: a larger selection goes in several calls

const placeRow = (place) => {
  const row = {};
  for (const key of FIELDS) {
    const value = place[key];
    if (value !== null && value !== undefined && value !== "") row[key] = value;
  }
  return row;
};

// The bodies to send, in slices the server accepts. Only what the map published; the attestation is the person's own.
export function addManyBodies(places, { approve = true, checkWebsite = false } = {}) {
  const rows = (places || []).map(placeRow);
  const out = [];
  for (let i = 0; i < rows.length; i += MAX_PER_REQUEST) {
    out.push({ places: rows.slice(i, i + MAX_PER_REQUEST), attestation: true, approve, check_website: Boolean(checkWebsite) });
  }
  return out;
}

const ADD_KEYS = ["requested", "created", "already_known", "in_crm", "waiting_review", "kept_rejected", "suppressed", "unreadable", "sites_checked"];

// The answers of several slices, added up (only the server's numbers).
export function sumAdded(answers) {
  const total = Object.fromEntries(ADD_KEYS.map((k) => [k, 0]));
  total.lead_ids = [];
  for (const a of answers || []) {
    for (const k of ADD_KEYS) total[k] += Number(a[k]) || 0;
    total.lead_ids.push(...(a.lead_ids || []));
  }
  return total;
}

// What really happened, in French, from the server's counts. Nothing was sent; a zero line is left out.
export function describeAddedMany(t) {
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const lines = [];
  if (t.in_crm) lines.push(`${plural(t.in_crm, "établissement est", "établissements sont")} dans votre CRM.`);
  if (t.waiting_review) lines.push(`${plural(t.waiting_review, "attend", "attendent")} votre relecture (« À traiter »).`);
  if (t.created || t.already_known) lines.push(`${t.created} nouveau(x), ${t.already_known} déjà connu(s) : rien n'est dupliqué.`);
  if (t.kept_rejected) lines.push(`${plural(t.kept_rejected, "était rejeté", "étaient rejetés")} par une personne : laissé(s) tel(s) quel(s).`);
  if (t.suppressed) lines.push(`${plural(t.suppressed, "figure", "figurent")} sur votre liste d'opposition : non ajouté(s).`);
  if (t.unreadable) lines.push(`${plural(t.unreadable, "ligne illisible", "lignes illisibles")} : non ajoutée(s).`);
  lines.push("Rien n'a été envoyé.");
  return lines;
}
