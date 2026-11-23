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

const CASES = (offer = null) => ({
  configured: Boolean(offer), language: "fr", default: offer ? "seo_geo" : null,
  cases: [
    { kind: "refonte_maintenance", label: "Refonte et maintenance de site web ou d'application mobile", when: "Prospects dont le site n'a pas répondu à la dernière vérification.", configured: false, offer: null },
    { kind: "creation", label: "Création et conception de site web ou d'application mobile", when: "Prospects sans site identifié après recherche dans leur annuaire.", configured: false, offer: null },
    { kind: "seo_geo", label: "SEO / GEO et présence en ligne, y compris la visibilité dans les IA", when: "Prospects dont le site existe.", configured: Boolean(offer), offer },
  ],
});
const typeInto = async (id, value) => {
  const el = byId(id);
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
};

test("each offer says who receives it, and only the complete ones are saved with their default", async () => {
  answer({ "/settings/offers": CASES() });
  api.put.mockResolvedValue({ data: CASES() });
  await show(<Offer />);
  expect(byId("offers-when").textContent).toContain("site n'a pas répondu"); // the first case and who receives it
  await act(async () => byId("offers-tab-creation").click());
  expect(byId("offers-when").textContent).toContain("sans site identifié après recherche");
  await typeInto("offers-name", "Création de site");
  await typeInto("offers-pitch", "Un site clair qui présente votre activité et vos horaires.");
  await typeInto("offers-cta", "Un appel de 15 minutes ?");
  await act(async () => byId("offers-default").click());
  await act(async () => byId("offers-save").form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(api.put).toHaveBeenCalledWith("/settings/offers", {
    language: "fr", default: "creation",
    offers: { creation: { name: "Création de site", pitch: "Un site clair qui présente votre activité et vos horaires.", cta: "Un appel de 15 minutes ?" } },
  });
});

test("an incomplete default offer is refused before anything is sent", async () => {
  answer({ "/settings/offers": CASES() });
  await show(<Offer />);
  await act(async () => byId("offers-save").form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(byId("offers-error").textContent).toContain("L'offre par défaut doit être complète");
  expect(api.put).not.toHaveBeenCalled();
});

test("a member reads the offers but cannot edit them", async () => {
  global.__user = member;
  answer({ "/settings/offers": CASES({ name: "SEO local", pitch: "Être trouvé sur les moteurs, les cartes et les assistants IA.", cta: "Un appel" }) });
  await show(<Offer />);
  await act(async () => byId("offers-tab-seo_geo").click());
  expect(byId("offers-name").disabled).toBe(true);
  expect(byId("offers-save").disabled).toBe(true);
  expect(byId("offers-name").value).toBe("SEO local");
});
