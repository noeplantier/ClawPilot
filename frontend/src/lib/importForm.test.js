import { describeImport, fileProblem, formatFromFilename, validateImportForm } from "@/lib/importForm";

const OK = {
  content: "name\nA", format: "csv", origin: "Export of my own customer CRM", legal_basis: "legitimate_interest_b2b",
  legal_basis_note: "", country: "FR", language: "fr", vertical: "restaurants",
};

test("a complete form passes", () => {
  expect(validateImportForm(OK).ok).toBe(true);
});

test.each([
  [{ content: "" }, "content"],
  [{ format: "xml" }, "format"],
  [{ origin: "list" }, "origin"],
  [{ legal_basis: "because" }, "legal_basis"],
  [{ country: "FRA" }, "country"],
  [{ language: "f" }, "language"],
  [{ vertical: "  " }, "vertical"],
])("%j is refused on %s", (patch, field) => {
  const out = validateImportForm({ ...OK, ...patch });
  expect(out.ok).toBe(false);
  expect(out.errors[field]).toBeTruthy();
});

test("the legal basis 'other' must be explained", () => {
  expect(validateImportForm({ ...OK, legal_basis: "other" }).errors.legal_basis_note).toMatch(/Explain/);
  expect(validateImportForm({ ...OK, legal_basis: "other", legal_basis_note: "Signed partnership agreement" }).ok).toBe(true);
});

test("file checks: extension and size", () => {
  expect(formatFromFilename("Clients.CSV")).toBe("csv");
  expect(formatFromFilename("a.json")).toBe("json");
  expect(formatFromFilename("a.xlsx")).toBeNull();
  expect(fileProblem({ name: "a.xlsx", size: 10 })).toMatch(/\.csv or \.json/);
  expect(fileProblem({ name: "a.csv", size: 3_000_000 })).toMatch(/too large/);
  expect(fileProblem({ name: "a.csv", size: 1000 })).toBeNull();
});

test("the summary uses the server counts and says 'would' for a preview only", () => {
  const r = { rows_total: 6, rows_valid: 4, duplicates_merged: 1, suppressed: 1, errors_count: 2, created: 2, updated: 0, preview: true };
  expect(describeImport(r)).toBe(
    "4 valid rows of 6, 1 duplicate merged, 1 skipped (on the do-not-contact list), 2 rows rejected. would create 2 prospects, would update 0."
  );
  expect(describeImport({ ...r, preview: false })).toMatch(/created 2 prospects, updated 0\.$/);
});
