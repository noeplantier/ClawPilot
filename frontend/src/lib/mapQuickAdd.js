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
  if (siteAsked) {
    lines.push(out.website_checked ? "Its website was read." : "Its website could not be read (blocked by its robots.txt, unreachable, or over the limit): that says nothing about its e-mail.");
  }
  return lines;
}
