// Le Composer IA, sans réseau : l'offre réelle remplace tout produit inventé, la fenêtre défile, et l'envoi à un lead passe par une
// confirmation puis par POST /messages/email (un seul destinataire), jamais avant.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import AIComposerModal from "@/components/AIComposerModal";

global.IS_REACT_ACT_ENVIRONMENT = true;

const OFFER = { name: "Refonte de site", pitch: "Un site rapide, clair et à jour, maintenu chaque mois.", cta: "Un appel de 15 minutes ?" };
const OFFERS = { configured: true, language: "fr", default: "refonte_maintenance", cases: [
  { kind: "refonte_maintenance", label: "Refonte", when: "w", configured: true, offer: OFFER },
  { kind: "creation", label: "Création", when: "w", configured: false, offer: null },
] };
const LEAD = { id: "l1", email: "contact@vng.example" };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.post].forEach((m) => m.mockReset());
  Object.values(toast).forEach((m) => m.mockReset());
  api.get.mockResolvedValue({ data: OFFERS });
  api.post.mockImplementation((url) => Promise.resolve({ data: url === "/ai/generate"
    ? { subject: "Votre site, VNG Informatique", body: "Bonjour Jean,\n\nUn site rapide…", language: "fr" }
    : { result: { status: "sent" } } }));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show(defaults) {
  await act(async () => { root.render(<MemoryRouter><AIComposerModal open onClose={() => {}} defaults={defaults} /></MemoryRouter>); });
  await act(async () => {});
}
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

test("the offer comes from your settings, never an invented product, and the window scrolls instead of overflowing", async () => {
  await show({ recipient_name: "Jean", company: "VNG Informatique", lead: LEAD });
  expect(q("ai-product-input").value).toBe("Refonte de site : Un site rapide, clair et à jour, maintenu chaque mois.");
  expect(q("ai-goal-input").value).toBe("Un appel de 15 minutes ?");
  expect(q("ai-language-select").value).toBe("fr");
  expect(document.body.textContent).not.toMatch(/OutreachOS lead generation|gemini/i);
  expect(q("ai-composer-modal").className).toMatch(/max-h-\[92vh\]/);
  expect(q("ai-composer-modal").className).toMatch(/overflow-y-auto/);
});

test("a lead's message is sent to that one address only after a confirmation", async () => {
  await show({ recipient_name: "Jean", company: "VNG Informatique", lead: LEAD });
  await act(async () => q("ai-generate-button").click());
  const generated = api.post.mock.calls.find(([url]) => url === "/ai/generate")[1];
  expect(generated).not.toHaveProperty("lead"); // the e-mail never reaches the AI provider
  expect(JSON.stringify(generated)).not.toContain(LEAD.email);
  expect(q("ai-send").textContent).toContain(LEAD.email);
  await act(async () => q("ai-send").click());
  expect(api.post.mock.calls.some(([url]) => url === "/messages/email")).toBe(false); // nothing leaves before the confirmation
  expect(q("ai-send-confirm").textContent).toContain("Un seul destinataire");
  await act(async () => q("ai-send-go").click());
  expect(api.post).toHaveBeenCalledWith("/messages/email", { to: LEAD.email, subject: "Votre site, VNG Informatique", body: "Bonjour Jean,\n\nUn site rapide…", lead_id: "l1" });
  expect(q("ai-sent").textContent).toContain("Accepté par le fournisseur");
  expect(q("ai-sent").textContent).not.toMatch(/livré|delivered/i);
});

test("a refusal is shown with the server's reason, and without a lead there is no send button", async () => {
  api.post.mockImplementation((url) => (url === "/ai/generate"
    ? Promise.resolve({ data: { subject: "S", body: "B", language: "fr" } })
    : Promise.reject({ response: { data: { detail: { code: "provider_not_configured", message: "SMTP injoignable depuis ce serveur." } } } })));
  await show({ recipient_name: "Jean", company: "VNG", lead: LEAD });
  await act(async () => q("ai-generate-button").click());
  await act(async () => q("ai-send").click());
  await act(async () => q("ai-send-go").click());
  expect(toast.error).toHaveBeenCalledWith("SMTP injoignable depuis ce serveur.");
  expect(q("ai-sent")).toBeNull();

  await act(async () => root.render(<MemoryRouter><AIComposerModal open onClose={() => {}} defaults={{ recipient_name: "X", company: "Y" }} /></MemoryRouter>));
  await act(async () => {});
  await act(async () => q("ai-generate-button").click());
  expect(q("ai-send")).toBeNull();
});
