// Pure helpers of the three offers (no network). Nothing is invented: a template only carries the organisation's own words
// (the offer's name, pitch and next step) and the recipient's tokens, never a claim about the prospect.
export const OFFER_LIMITS = { name: [2, 120], pitch: [20, 600], cta: [3, 160] };

export const isComplete = (o) =>
  Boolean(o) && Object.entries(OFFER_LIMITS).every(([k, [low, high]]) => typeof o[k] === "string" && o[k].trim().length >= low && o[k].trim().length <= high);

// The body sent to PUT /settings/offers: only the complete offers; the default must be one of them.
export function offersBody(forms, defaultKind, language) {
  const offers = {};
  for (const [kind, o] of Object.entries(forms || {})) {
    if (isComplete(o)) offers[kind] = { name: o.name.trim(), pitch: o.pitch.trim(), cta: o.cta.trim() };
  }
  if (!offers[defaultKind]) return { ok: false, error: "L'offre par défaut doit être complète (nom, description, prochaine étape)." };
  return { ok: true, body: { language: language || "fr", default: defaultKind, offers } };
}

// The subject and message of a batch, from the chosen offer: its own words and the tokens, no sentence about the prospect.
export function prefillFromOffer(offer, language = "fr") {
  if (!isComplete(offer)) return null;
  const hello = language === "en" ? "Hello {{first_name}}," : "Bonjour {{first_name}},";
  return {
    subject: `${offer.name.trim()} · {{company}}`,
    body: `${hello}\n\n${offer.pitch.trim()}\n\n${offer.cta.trim()}`,
  };
}

// The offers a batch can use: the configured cases, in the order of the API.
export const usableOffers = (data) => ((data && data.cases) || []).filter((c) => c.configured && c.offer);
