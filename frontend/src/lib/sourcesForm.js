// Form rules and wording for the Sources page. Zod mirrors the API's own checks; the server stays the authority.
import { z } from "zod";

export const PAGE_SIZE = 25;
export const VERTICAL_LABELS = {
  restaurants: "Restaurants, cafés, bars", bakeries: "Bakeries, pastry", beauty: "Hairdressers, beauty", hotels: "Hotels, guest houses",
  shops: "Shops", crafts: "Crafts", offices: "Offices (law, accounting, real estate…)",
};

const num = (v) => (v === "" || v === null || v === undefined ? undefined : Number(v));

export function schemaFor(provider) {
  const network = provider.kind === "network";
  return z
    .object({
      vertical: z.string().refine((v) => provider.verticals.includes(v), "This source does not cover that vertical"),
      limit: z.number({ invalid_type_error: "Limit must be a number" }).int().min(1, "At least 1").max(100, "At most 100"),
      country: z.string().regex(/^[A-Za-z]{2}$/, "Two-letter country code, e.g. FR").optional().or(z.literal("")),
      city: z.string().max(80).optional().or(z.literal("")),
      lat: z.number({ invalid_type_error: "Latitude must be a number" }).min(-90).max(90).optional(),
      lon: z.number({ invalid_type_error: "Longitude must be a number" }).min(-180).max(180).optional(),
      radius_m: z.number({ invalid_type_error: "Radius must be a number" }).int().min(100, "At least 100 m").max(provider.max_radius_m, `At most ${provider.max_radius_m} m`),
    })
    .superRefine((v, ctx) => {
      if ((v.lat === undefined) !== (v.lon === undefined)) ctx.addIssue({ code: "custom", path: ["lat"], message: "Latitude and longitude go together" });
      if (network && v.lat === undefined) ctx.addIssue({ code: "custom", path: ["lat"], message: "Pick a town or enter a position" });
      if (network && !v.country) ctx.addIssue({ code: "custom", path: ["country"], message: "Country is required for this source" });
    });
}

// -> { ok: true, body } | { ok: false, errors: { field: message } }
export function validateDiscover(provider, raw) {
  const parsed = schemaFor(provider).safeParse({
    vertical: raw.vertical, limit: num(raw.limit), country: (raw.country || "").trim(), city: (raw.city || "").trim(),
    lat: num(raw.lat), lon: num(raw.lon), radius_m: num(raw.radius_m),
  });
  if (!parsed.success) {
    const errors = {};
    for (const issue of parsed.error.issues) if (!errors[issue.path[0] || "form"]) errors[issue.path[0] || "form"] = issue.message;
    return { ok: false, errors };
  }
  const v = parsed.data;
  const body = { provider: provider.name, vertical: v.vertical, limit: v.limit, radius_m: v.radius_m };
  if (v.country) body.country = v.country.toUpperCase();
  if (v.city) body.city = v.city;
  if (v.lat !== undefined) { body.lat = v.lat; body.lon = v.lon; }
  return { ok: true, body };
}

// What was found, in exact numbers; a zero is said plainly.
export function resultSummary(out) {
  if (out.total === 0) return "No place found for these parameters.";
  const dup = out.duplicates_merged ? `, ${out.duplicates_merged} duplicate${out.duplicates_merged === 1 ? "" : "s"} merged` : "";
  const more = out.truncated ? " The source holds more: narrow the area to see the rest." : "";
  return `${out.total} place${out.total === 1 ? "" : "s"}${dup}.${more}`;
}

// Signals worth showing on a row: detected ones (a finding) and nothing else; "unknown" is never turned into a verdict.
export const detectedSignals = (place) => place.signals.filter((s) => s.state === "detected");
export const unknownCount = (place) => place.signals.filter((s) => s.state === "unknown").length;

export const hasContact = (p) => Boolean(p.email || p.phone || p.website);
