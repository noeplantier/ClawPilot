// The to-enrich queue, the draft progress line and the offer form: explicit states, honest wording, role-gated actions.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import ToEnrich from "@/pages/ToEnrich";
import Offer from "@/pages/Offer";
import DraftJobsStrip from "@/components/outreach/DraftJobsStrip";
import DraftJobStatus from "@/components/outreach/DraftJobStatus";

global.IS_REACT_ACT_ENVIRONMENT = true;
const owner = { id: "u1", role: "owner" };
const member = { id: "u2", role: "member" };
const COUNTS = { queued: 0, generating: 0, ready: 0, failed: 0, unavailable: 0, offer_required: 0 };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.post, api.put].forEach((f) => f.mockReset());
  window.localStorage.clear();
  global.__user = owner;
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const answer = (table) =>
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(`unexpected GET ${url}`))));
const show = async (ui) => {
  await act(async () => root.render(<MemoryRouter>{ui}</MemoryRouter>));
  await act(async () => {});
};
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

test("the to-enrich queue says what each prospect lacks, and nothing about the ones that are qualified", async () => {
  answer({
    "/prospects/to-enrich": {
      total: 2, limit: 25, offset: 0,
      items: [
        { id: "p1", name: "Chez Alice", city: "Plérin", email: "a@alice.fr", phone: null, review_status: "pending", missing_fields: ["phone_missing", "address_missing"] },
        { id: "p2", name: "Bar du Port", city: null, email: null, phone: null, review_status: null, missing_fields: ["email_missing", "mystery_gap"] },
      ],
    },
  });
  await show(<ToEnrich />);
  const rows = [...container.querySelectorAll('[data-testid="to-enrich-row"]')];
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toContain("Missing: phone, address");
  expect(rows[0].getAttribute("href")).toBe("/app/prospects/p1");
  expect(rows[1].textContent).toContain("Missing: e-mail, mystery_gap"); // an unknown gap is shown, not hidden
  expect(rows[1].textContent).toContain("No contact detail known");
});

test("an empty queue is said plainly", async () => {
  answer({ "/prospects/to-enrich": { items: [], total: 0, limit: 25, offset: 0 } });
  await show(<ToEnrich />);
  expect(byId("empty-block").textContent).toContain("Nothing waits to be enriched");
});

test("without an offer the progress line asks for one and never pretends a draft exists", async () => {
  answer({ "/prospects/draft-jobs/summary": { counts: { ...COUNTS, offer_required: 3 }, offer_configured: false, ai_active: true } });
  await show(<DraftJobsStrip />);
  expect(byId("draft-jobs-strip").textContent).toContain("3 need an offer");
  expect(byId("draft-offer-required").textContent).toContain("Offer required");
  expect(byId("draft-offer-required").querySelector("a").getAttribute("href")).toBe("/app/settings/offer");
  expect(byId("draft-jobs-run")).toBeNull(); // nothing to run without an offer
});

test("with the AI off the drafts wait, say so, and can be resumed by someone allowed to decide", async () => {
  const summary = { counts: { ...COUNTS, unavailable: 2, ready: 1 }, offer_configured: true, ai_active: false };
  answer({ "/prospects/draft-jobs/summary": summary });
  api.post.mockResolvedValue({ data: summary });
  await show(<DraftJobsStrip />);
  expect(byId("draft-jobs-strip").textContent).toContain("1 ready · 2 waiting for the AI");
  expect(byId("draft-ai-off").textContent).toContain("Nothing is written in its place");
  await act(async () => byId("draft-jobs-run").click());
  expect(api.post).toHaveBeenCalledWith("/prospects/draft-jobs/run");
});

test("a member can read the progress but not start the preparation", async () => {
  global.__user = member;
  answer({ "/prospects/draft-jobs/summary": { counts: { ...COUNTS, failed: 1 }, offer_configured: true, ai_active: true } });
  await show(<DraftJobsStrip />);
  expect(byId("draft-jobs-strip").textContent).toContain("1 failed");
  expect(byId("draft-jobs-run")).toBeNull();
});

test("one prospect's draft shows its state, the website wording that is known, and why it is not ready", async () => {
  answer({
    "/prospects/p1/draft-job": { id: "j1", lead_id: "p1", status: "unavailable", site_state: "unknown", language: "fr", attempts: 1, error: "The AI composer is off: AI_PROVIDER is not set.", draft_id: null },
  });
  await show(<DraftJobStatus prospectId="p1" />);
  const box = byId("draft-job-status");
  expect(box.textContent).toContain("Draft waiting for the AI");
  expect(box.textContent).toContain("Website not checked"); // never "no website" from an empty field
  expect(box.textContent).toContain("The AI composer is off");
});

test("the offer form stays disabled until the offer is complete and saves exactly what was typed", async () => {
  answer({ "/settings/offer": { configured: false, offer: null } });
  api.put.mockResolvedValue({ data: { configured: true, offer: {} } });
  await show(<Offer />);
  expect(byId("offer-save").disabled).toBe(true);
  const type = async (id, value) => {
    const el = byId(id);
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    await act(async () => {
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  await type("offer-name", "Site vitrine");
  await type("offer-pitch", "Un site clair avec réservation intégrée.");
  await type("offer-cta", "Un appel de 15 minutes");
  expect(byId("offer-save").disabled).toBe(false);
  await act(async () => byId("offer-save").form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(api.put).toHaveBeenCalledWith("/settings/offer", { name: "Site vitrine", pitch: "Un site clair avec réservation intégrée.", cta: "Un appel de 15 minutes", language: "fr" });
});

test("a member cannot edit the offer", async () => {
  global.__user = member;
  answer({ "/settings/offer": { configured: true, offer: { name: "Site vitrine", pitch: "Un site clair avec réservation intégrée.", cta: "Un appel", language: "fr" } } });
  await show(<Offer />);
  expect(byId("offer-name").disabled).toBe(true);
  expect(byId("offer-save").disabled).toBe(true);
  expect(byId("offer-name").value).toBe("Site vitrine");
});
