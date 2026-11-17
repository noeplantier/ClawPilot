// L'envoi par lots, sans réseau : aucune phrase inventée par défaut, l'offre choisie remplit le message avec ses propres mots.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", role: "owner" } }) }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import { clear } from "@/lib/swr";
import BatchComposerModal from "@/components/BatchComposerModal";

global.IS_REACT_ACT_ENVIRONMENT = true;

const OFFER = { name: "Création de site", pitch: "Un site clair qui présente votre activité et vos horaires.", cta: "Un appel de 15 minutes ?" };
const OFFERS = { configured: true, language: "fr", default: "creation", cases: [
  { kind: "refonte_maintenance", label: "Refonte", when: "Prospects dont le site n'a pas répondu à la dernière vérification.", configured: false, offer: null },
  { kind: "creation", label: "Création", when: "Prospects sans site identifié après recherche dans leur annuaire.", configured: true, offer: OFFER },
  { kind: "seo_geo", label: "SEO / GEO", when: "Prospects dont le site existe.", configured: false, offer: null },
] };

let container;
let root;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.post].forEach((m) => m.mockReset());
  Object.values(toast).forEach((m) => m.mockReset());
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/settings/offers" ? OFFERS : [{ id: "l1", full_name: "Ana Martin", company: "Boulangerie A", email: "ana@a.example" }] }));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show() {
  await act(async () => { root.render(<MemoryRouter><BatchComposerModal open onClose={() => {}} /></MemoryRouter>); });
  await act(async () => {});
}
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

test("no invented sentence by default: the message starts empty", async () => {
  await show();
  expect(q("batch-subject").value).toBe("");
  expect(document.body.textContent).not.toMatch(/scaling fast/i);
});

test("only the complete offers are offered, with who they are for, and the chosen one fills the message with its own words", async () => {
  await show();
  expect(q("batch-offer-seo_geo")).toBeNull();
  expect(q("batch-offer-creation").textContent).toContain("sans site identifié après recherche");
  await act(async () => q("batch-offer-creation").click());
  expect(q("batch-subject").value).toBe("Création de site · {{company}}");
  expect(q("batch-offer-creation").getAttribute("aria-checked")).toBe("true");
});

test("AI writing waits for an offer: it never presents another product", async () => {
  await show();
  await act(async () => q("batch-ai-button").click());
  expect(api.post).not.toHaveBeenCalled();
  expect(toast.error).toHaveBeenCalledWith("Choisissez d'abord l'offre de ce lot (étape 1).");
  await act(async () => q("batch-offer-creation").click());
  api.post.mockResolvedValue({ data: { subject: "S", body: "B" } });
  await act(async () => q("batch-ai-button").click());
  expect(api.post).toHaveBeenCalledWith("/ai/generate", expect.objectContaining({ product: `Création de site : ${OFFER.pitch}`, goal: OFFER.cta }));
});
