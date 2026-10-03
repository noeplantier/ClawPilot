/* global HTMLSelectElement, HTMLInputElement, MouseEvent, File */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
let mockUser = { role: "owner" };
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

import { api } from "@/lib/api";
import ProspectImport from "@/pages/ProspectImport";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

function setup({ flag = true, batches = [], role = "owner" } = {}) {
  mockUser = { role };
  api.get.mockImplementation((url) =>
    Promise.resolve({ data: url === "/prospects/settings" ? { flags: { prospect_import: flag }, usage: {}, sender_configured: true } : batches })
  );
}

async function show() {
  await act(async () => root.render(<MemoryRouter><ProspectImport /></MemoryRouter>));
  await act(async () => {});
}

const type = async (id, value) => {
  const el = byId(id);
  const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
};

const click = (id) => act(async () => { byId(id).dispatchEvent(new MouseEvent("click", { bubbles: true })); });

async function chooseFile() {
  const file = new File(["name\nAtelier"], "clients.csv", { type: "text/csv" });
  file.text = () => Promise.resolve("name\nAtelier");
  await act(async () => {
    Object.defineProperty(byId("import-file"), "files", { value: [file], configurable: true });
    byId("import-file").dispatchEvent(new Event("change", { bubbles: true }));
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("when the flag is off the page says so and shows no form", async () => {
  setup({ flag: false });
  await show();
  expect(byId("import-disabled").textContent).toContain("FEATURE_PROSPECT_IMPORT");
  expect(byId("import-form")).toBeNull();
  expect(byId("import-history-empty")).not.toBeNull(); // explicit empty state, no invented rows
});

test("a member cannot import", async () => {
  setup({ role: "member" });
  await show();
  expect(byId("import-forbidden")).not.toBeNull();
  expect(byId("import-form")).toBeNull();
});

test("the form refuses to call the API until it is valid", async () => {
  setup();
  await show();
  await click("import-preview");
  expect(api.post).not.toHaveBeenCalled();
  expect(byId("file-error").textContent).toMatch(/Choose a CSV/);
  expect(byId("origin-error")).not.toBeNull();
});

test("preview first, then import only after the attestation", async () => {
  setup();
  api.post.mockResolvedValueOnce({
    data: { preview: true, rows_total: 1, rows_valid: 1, errors_count: 0, errors: [], ignored_columns: [], entities: 1, duplicates_merged: 0, suppressed: 0, created: 1, updated: 0, already_imported: false },
  });
  await show();
  await chooseFile();
  await type("import-origin", "Export of my own customer CRM");
  await type("import-vertical", "artisans");
  await type("import-basis", "legitimate_interest_b2b");
  await click("import-preview");

  const [url, body] = api.post.mock.calls[0];
  expect(url).toBe("/prospect-imports");
  expect(body).toMatchObject({ preview: true, attestation: false, format: "csv", filename: "clients.csv", legal_basis: "legitimate_interest_b2b" });
  expect(byId("import-summary").textContent).toContain("would create 1 prospect");
  expect(byId("import-commit").disabled).toBe(true); // not until the attestation is ticked

  api.post.mockResolvedValueOnce({
    data: { preview: false, batch_id: "b1", rows_total: 1, rows_valid: 1, errors_count: 0, errors: [], ignored_columns: [], entities: 1, duplicates_merged: 0, suppressed: 0, created: 1, updated: 0, already_imported: false },
  });
  await act(async () => { byId("import-attest").click(); });
  expect(byId("import-commit").disabled).toBe(false);
  await click("import-commit");
  expect(api.post.mock.calls[1][1]).toMatchObject({ preview: false, attestation: true });
});

test("a server refusal is shown as a sentence", async () => {
  setup();
  api.post.mockRejectedValueOnce({ response: { status: 403, data: { detail: { code: "feature_disabled", message: "Prospect import is off (FEATURE_PROSPECT_IMPORT)" } } } });
  await show();
  await chooseFile();
  await type("import-origin", "Export of my own customer CRM");
  await type("import-vertical", "artisans");
  await type("import-basis", "consent");
  await click("import-preview");
  expect(byId("import-api-error").textContent).toContain("Prospect import is off");
});
