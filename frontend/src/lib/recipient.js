// The recipient of a one-off message: a real e-mail must be linked to a lead record of the organisation (the server refuses
// otherwise, because the unsubscribe link in its footer belongs to that record). Pure helpers, no network.

const emailKey = (v) => String(v || "").trim().toLowerCase();
const phoneKey = (v) => String(v || "").replace(/[^\d]/g, "");

// What identifies a recipient on this channel: the e-mail address, or the phone number's digits.
export const keyOf = (channel, value) => (channel === "email" ? emailKey(value) : phoneKey(value));
export const addressOf = (channel, lead) => (channel === "email" ? lead.email : lead.phone) || "";

// The lead that owns exactly what was typed (never a fuzzy match: the message goes to this address).
export function matchLead(leads, typed, channel) {
  const key = keyOf(channel, typed);
  if (!key) return null;
  return (leads || []).find((l) => keyOf(channel, addressOf(channel, l)) === key) || null;
}

// Leads to offer while typing: those that have an address on this channel and whose name, company or address contains the text.
// The API lists the hottest first and the order is kept.
export function suggestLeads(leads, typed, channel, limit = 6) {
  const q = String(typed || "").trim().toLowerCase();
  return (leads || [])
    .filter((l) => addressOf(channel, l))
    .filter((l) => !q || [l.full_name, l.company, addressOf(channel, l)].some((v) => String(v || "").toLowerCase().includes(q)))
    .slice(0, limit);
}

export const looksLikeEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || "").trim());

// Why the message cannot go yet, or null. For e-mail the address must belong to a lead; WhatsApp is checked by the server.
export function sendBlock(channel, typed, lead, leadsLoaded) {
  if (channel !== "email") return null;
  if (!leadsLoaded) return "Loading your leads…";
  if (!looksLikeEmail(typed)) return null; // nothing to explain yet
  return lead ? null : "not-a-lead";
}
