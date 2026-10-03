// Validation and wording for the prospect-list import form. Zod mirrors the API's own rules so mistakes are caught
// before upload; the server remains the authority.
import { z } from "zod";

export const MAX_BYTES = 2_000_000;
export const MAX_ROWS = 1000;

export const LEGAL_BASES = [
  { value: "legitimate_interest_b2b", label: "Legitimate interest (B2B, relevant to the recipient's profession)" },
  { value: "consent", label: "Consent of the people concerned" },
  { value: "contract", label: "Existing contract / customer relationship" },
  { value: "other", label: "Other (explain below)" },
];

export const importFormSchema = z
  .object({
    content: z.string().min(1, "Choose a CSV or JSON file"),
    format: z.enum(["csv", "json"], { errorMap: () => ({ message: "The file must be .csv or .json" }) }),
    origin: z.string().trim().min(10, "Say where this list comes from (at least 10 characters)").max(1000),
    legal_basis: z.enum(["legitimate_interest_b2b", "consent", "contract", "other"], {
      errorMap: () => ({ message: "Choose a legal basis" }),
    }),
    legal_basis_note: z.string().max(1000).optional().or(z.literal("")),
    country: z.string().regex(/^[A-Za-z]{2}$/, "Two-letter country code, e.g. FR"),
    language: z.string().regex(/^[A-Za-z]{2}$/, "Two-letter language code, e.g. fr"),
    vertical: z.string().trim().min(1, "Give the activity of these companies").max(60),
  })
  .refine((v) => v.legal_basis !== "other" || (v.legal_basis_note || "").trim().length >= 10, {
    path: ["legal_basis_note"],
    message: "Explain the legal basis (at least 10 characters)",
  });

// -> { ok: true, data } | { ok: false, errors: { field: message } }
export function validateImportForm(values) {
  const parsed = importFormSchema.safeParse(values);
  if (parsed.success) return { ok: true, data: parsed.data };
  const errors = {};
  for (const issue of parsed.error.issues) {
    const key = issue.path[0] || "form";
    if (!errors[key]) errors[key] = issue.message;
  }
  return { ok: false, errors };
}

export function formatFromFilename(name) {
  const lower = (name || "").toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".json")) return "json";
  return null;
}

export function fileProblem(file) {
  if (!file) return null;
  if (!formatFromFilename(file.name)) return "The file must be .csv or .json";
  if (file.size > MAX_BYTES) return `The file is too large (${Math.round(file.size / 1000)} kB, maximum ${MAX_BYTES / 1000} kB)`;
  return null;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// One honest sentence about a preview or an import. Counts come from the server; nothing is estimated here.
export function describeImport(r) {
  const parts = [
    `${plural(r.rows_valid, "valid row")} of ${r.rows_total}`,
    r.duplicates_merged ? `${plural(r.duplicates_merged, "duplicate")} merged` : null,
    r.suppressed ? `${r.suppressed} skipped (on the do-not-contact list)` : null,
    r.errors_count ? `${plural(r.errors_count, "row")} rejected` : null,
  ].filter(Boolean);
  const verb = r.preview ? ["would create", "would update"] : ["created", "updated"];
  return `${parts.join(", ")}. ${verb[0]} ${plural(r.created, "prospect")}, ${verb[1]} ${r.updated}.`;
}
