// Batches (what ran and how it is going) and AI drafts (what is waiting for a person): real data or an explicit empty state.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", role: "owner" } }) }));

import { api } from "@/lib/api";
import Batches from "@/pages/Batches";
import Drafts from "@/pages/Drafts";

global.IS_REACT_ACT_ENVIRONMENT = true;
const COUNTS = { queued: 0, generating: 0, ready: 2, failed: 0, unavailable: 0, offer_required: 0 };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  window.localStorage.clear();
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const answer = (table) =>
  api.get.mockImplementation((url) => {
    const hit = Object.entries(table).find(([k]) => url === k);
    return hit ? Promise.resolve({ data: hit[1] }) : Promise.reject(new Error(`unexpected GET ${url}`));
  });
const show = async (ui, path = "/") => {
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>));
  await act(async () => {});
};
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

test("batches lists what was really launched, newest first, with the three ways to launch and the queue", async () => {
  answer({
    "/map/search": [{ id: "s1", status: "succeeded", category: "restaurants", result_count: 12, created_at: "2026-11-04T10:00:00Z" }],
    "/prospect-imports": [{ id: "i1", filename: "lyon.csv", source_name: "import:ab", rows_total: 40, created_at: "2026-11-04T11:00:00Z", summary: { prospects_created: 31 } }],
    "/prospects/to-enrich": { items: [], total: 3, limit: 1, offset: 0 },
    "/prospects/draft-jobs/summary": { counts: COUNTS, offer_configured: true, ai_active: true },
  });
  await show(<Batches />);
  const rows = [...container.querySelectorAll('[data-testid="batches-row"]')];
  expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("lyon.csv"), expect.stringContaining("restaurants")]);
  expect(rows[0].textContent).toContain("40 rows, 31 new prospects");
  expect(rows[1].textContent).toContain("12 places saved");
  expect(byId("batches-queue").textContent).toContain("3 prospects wait");
  expect(byId("draft-jobs-strip").textContent).toContain("2 ready");
  for (const id of ["launch-map", "launch-import", "launch-sources"]) expect(byId(id)).not.toBeNull();
  expect(container.textContent).not.toMatch(/pause|resume|preset/i); // nothing is offered that no server engine does
});

test("batches with nothing launched says so instead of inventing a history", async () => {
  answer({
    "/map/search": [], "/prospect-imports": [],
    "/prospects/to-enrich": { items: [], total: 0, limit: 1, offset: 0 },
    "/prospects/draft-jobs/summary": { counts: { ...COUNTS, ready: 0 }, offer_configured: false, ai_active: false },
  });
  await show(<Batches />);
  expect(byId("empty-block").textContent).toContain("Nothing was launched yet");
  expect(byId("batches-queue").textContent).toContain("0 prospects wait");
});

test("the AI drafts list marks the automatic and the edited ones, opens the sheet, and no draft is shown as sent", async () => {
  answer({
    "/prospects/draft-jobs/summary": { counts: COUNTS, offer_configured: true, ai_active: true },
    "/prospects/drafts": { total: 2, limit: 25, offset: 0, items: [
      { id: "d1", lead_id: "p1", lead_name: "Chez Alice", city: "Plérin", subject: "Votre présence en ligne", status: "draft", auto: true, edited: false, dry_run: true, created_at: "2026-11-04T10:00:00Z" },
      { id: "d2", lead_id: "p2", lead_name: "Bar du Port", city: null, subject: "À propos du bar", status: "approved", auto: false, edited: true, dry_run: true, created_at: "2026-11-03T10:00:00Z" },
    ] },
  });
  await show(<Drafts />);
  const rows = [...container.querySelectorAll('[data-testid="draft-row"]')];
  expect(rows).toHaveLength(2);
  expect(rows[0].getAttribute("href")).toBe("/app/prospects/p1");
  expect(rows[0].textContent).toContain("AI");
  expect(rows[0].textContent).toContain("To review");
  expect(rows[1].textContent).toContain("Edited");
  expect(rows[1].textContent).not.toContain("AI");
  rows.forEach((r) => expect(r.textContent).not.toMatch(/\bsent\b/i)); // a draft is never shown as sent from this list
});

test("an organisation without any draft is told how to get one", async () => {
  answer({
    "/prospects/draft-jobs/summary": { counts: { ...COUNTS, ready: 0, offer_required: 2 }, offer_configured: false, ai_active: true },
    "/prospects/drafts": { total: 0, limit: 25, offset: 0, items: [] },
  });
  await show(<Drafts />);
  expect(byId("empty-block").textContent).toContain("Describe your offer");
});

test("the status tabs ask the server for that status", async () => {
  answer({
    "/prospects/draft-jobs/summary": { counts: COUNTS, offer_configured: true, ai_active: true },
    "/prospects/drafts": { total: 0, limit: 25, offset: 0, items: [] },
  });
  await show(<Drafts />, "/app/drafts?status=approved");
  const call = api.get.mock.calls.find(([url]) => url === "/prospects/drafts");
  expect(call[1].params).toMatchObject({ status: "approved", limit: 25, offset: 0 });
});
