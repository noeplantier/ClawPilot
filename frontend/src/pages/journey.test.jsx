// « Campagne par zone », sans navigateur ni réseau (l'API est mockée). Ce que ces tests figent : ouvrir l'écran ne crée, n'approuve
// et n'envoie rien ; le périmètre et la couverture réels sont affichés ; ce qui bloque dit quoi faire ; l'approbation envoie le
// contenu et le nombre qui ont été lus ; un refus du serveur est lisible ; le suivi ne dit jamais « livré ».
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import { clear } from "@/lib/swr";
import Journey from "@/pages/Journey";

global.IS_REACT_ACT_ENVIRONMENT = true;

const owner = { id: "u1", role: "owner", email: "o@x.example" };
const member = { id: "u2", role: "member", email: "m@x.example" };
const ZONE = { kind: "bbox", south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant", label: null };
const ITEM = (id, ok, blocking, extra = {}) => ({ id, ok, blocking, label: id, fix: null, link: null, ...extra });
const READY = { ready: true, items: [ITEM("offer", true, true), ITEM("identity", true, true), ITEM("provider", true, true), ITEM("mode", true, false, { note: "Sandbox actif : seuls 2 destinataires de la liste blanche reçoivent." })], blockers: [] };
const BLOCKED = { ready: false, items: [ITEM("offer", false, true, { label: "Offre à décrire", fix: "Pilotage › Offre : décrivez ce que vous vendez.", link: "/app/settings/offer" }), ITEM("replies", false, false, { label: "Réponses non lues : IMAP non configuré", fix: "Sans IMAP, une réponse n'arrête pas les envois." })], blockers: [] };
const SUMMARY = (over = {}) => ({
  campaign: { id: "J1", name: "Lyon 6 · restaurants", status: "draft" },
  zone: ZONE,
  coverage: { searched: true, places_found: 87, truncated: false, statement: "87 établissement(s) trouvé(s) par la recherche du 10/11/2026. Les résultats viennent des sources interrogées ; aucune source n'est exhaustive." },
  readiness: READY,
  audience: { selected: 14, sendable: 12, already_sent: 0, held_back: [{ lead_id: "p9", name: "Café Noir", problems: ["Champ vide : {{ville}}"] }], held_back_count: 1, exclusions: { opted_out: 1 }, exclusion_labels: { opted_out: "Opposition enregistrée" } },
  template: { version: 2, subject: "À propos de {{nom}}", body: "Bonjour,\n\n{{constat}}\n\n{{offre}}", content_hash: "abcd1234", problems: [], placeholders: ["nom", "activite", "ville", "constat", "offre"], footer_note: "Le pied du message (identité, origine des données, lien de désinscription) est ajouté par le serveur." },
  examples: [{ name: "Bistro Un", city: "Lyon", email: "b1@x.example", subject: "À propos de Bistro Un", body: "Bonjour,\n\nSauf erreur de ma part, je n'ai pas identifié de site officiel pour Bistro Un.", facts: [], site_state: "none_identified" }],
  volume: { messages: 12, daily_cap: 20, total_cap: 12 },
  sender: { configured: true, name: "Noé", company: "Plantiers", email: "founder@plantiers.example", provider: "SMTP Hostinger" },
  schedule: { first_at: "2026-11-12T08:00:00Z", last_at: "2026-11-12T13:00:00Z", timezone: "Europe/Paris", days: [{ date: "2026-11-12", count: 12 }] },
  approval: { approved: false, valid: false, reasons: [] },
  offer_configured: true,
  ...over,
});
const PROGRESS = (over = {}) => ({ status: "draft", paused: false, total: 0, done: 0, percent: null, states: {}, replies: {}, actions: [], approval_valid: false, ...over });

let container;
let root;
let table;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.post, api.put, api.patch].forEach((m) => m.mockReset());
  Object.values(toast).forEach((m) => m.mockReset());
  global.__user = owner;
  table = {
    "/journeys": { items: [] },
    "/journeys/readiness": { data: READY },
    "/journeys/J1": { data: SUMMARY() },
    "/journeys/J1/progress": { data: PROGRESS() },
  };
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(`unexpected GET ${url}`))));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show(path) {
  await act(async () => { root.render(<MemoryRouter initialEntries={[path]}><Journey /></MemoryRouter>); });
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const text = () => container.textContent;
const click = async (el) => { await act(async () => { el.click(); }); await act(async () => {}); };
const type = async (el, value) => {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set;
  await act(async () => { setter.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
};

describe("without a zone", () => {
  it("says where to start and creates nothing", async () => {
    await show("/app/journey");
    expect(byId("journey-empty")).not.toBeNull();
    expect(text()).toMatch(/Continuer vers la campagne/);
    expect(api.post).not.toHaveBeenCalled();
  });
  it("lists the campaigns by zone with honest counters", async () => {
    table["/journeys"] = { items: [{ id: "J1", name: "Lyon 6", status: "running", zone: ZONE, recipients: 12, planned: 5, sent: 3, created_at: "2026-11-10T08:00:00Z" }] };
    await show("/app/journey");
    expect(byId("journey-list").textContent).toMatch(/3 accepté\(s\)? par le serveur SMTP|3 accepté.* par le serveur SMTP/);
    expect(byId("journey-list").textContent).not.toMatch(/livré/i);
  });
});

describe("a zone arrives from the map", () => {
  const URL = "/app/journey?south=45.7&west=4.78&north=45.8&east=4.9&category=restaurant";
  it("shows the perimeter and the setup, and creates nothing by itself", async () => {
    table["/journeys/readiness"] = { data: BLOCKED };
    await show(URL);
    expect(byId("journey-zone-text").textContent).toMatch(/45\.700–45\.800° N/);
    expect(byId("setup-offer").textContent).toMatch(/décrivez ce que vous vendez/);
    expect(byId("setup-link-offer").getAttribute("href")).toBe("/app/settings/offer");
    expect(byId("setup-replies").textContent).toMatch(/ne bloque pas/);
    expect(api.post).not.toHaveBeenCalled();
  });
  it("creates the campaign with the zone of the address, then opens it", async () => {
    api.post.mockResolvedValue({ data: { data: { id: "J1", selected: 12, excluded: 2 } } });
    await show(URL);
    await click(byId("journey-create"));
    expect(api.post).toHaveBeenCalledWith("/journeys", { name: "Zone · restaurant", zone: { south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant" } });
    expect(byId("journey-detail")).not.toBeNull();
  });
  it("shows the server's sentence when the zone is refused", async () => {
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: "zone_too_large", message: "La zone est trop large : choisissez une commune." } } } });
    await show(URL);
    await click(byId("journey-create"));
    expect(byId("journey-error").textContent).toBe("La zone est trop large : choisissez une commune.");
  });
  it("a member cannot create it", async () => {
    global.__user = member;
    await show(URL);
    expect(byId("journey-create").disabled).toBe(true);
  });
});

describe("the approval screen", () => {
  it("reads zone, coverage, audience, exclusions, message, volume, sender and schedule from the server", async () => {
    await show("/app/journey?id=J1");
    expect(byId("journey-coverage").textContent).toMatch(/aucune source n'est exhaustive/);
    expect(byId("approval-audience").textContent).toMatch(/12.*peuvent recevoir.*1 retenus/);
    expect(byId("approval-exclusions").textContent).toMatch(/1 · Opposition enregistrée/);
    expect(byId("approval-held").textContent).toMatch(/Café Noir/);
    expect(byId("approval-template").textContent).toMatch(/Version 2/);
    expect(byId("approval-volume").textContent).toMatch(/12 messages, un par destinataire · au plus 20 par jour/);
    expect(byId("approval-sender").textContent).toMatch(/founder@plantiers\.example · via SMTP Hostinger/);
    expect(byId("approval-schedule").textContent).toMatch(/Europe\/Paris/);
    expect(byId("examples").textContent).toMatch(/Bistro Un/);
    expect(byId("template-footer-note").textContent).toMatch(/désinscription/);
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
  });

  it("approves what was read: the content hash and the number of messages, after a confirmation that names them", async () => {
    api.post.mockResolvedValue({ data: { data: { scheduled: 12, drafts: 12, first_at: "2026-11-12T08:00:00Z", last_at: "2026-11-12T13:00:00Z" } } });
    await show("/app/journey?id=J1");
    await click(byId("approve-open"));
    expect(byId("approve-confirm-text").textContent).toMatch(/12 messages \(version 2\), pas davantage/);
    expect(api.post).not.toHaveBeenCalled(); // opening the confirmation approves nothing
    await click(byId("approve-confirm"));
    expect(api.post).toHaveBeenCalledWith("/journeys/J1/approve", { content_hash: "abcd1234", expected_count: 12 });
    expect(toast.success.mock.calls[0][0]).toMatch(/12 messages planifiés, aucun n'est parti/);
  });

  it("closes the button and says what is missing while the setup is incomplete", async () => {
    table["/journeys/J1"] = { data: SUMMARY({ readiness: BLOCKED }) };
    await show("/app/journey?id=J1");
    expect(byId("approve-open").disabled).toBe(true);
    expect(byId("approve-block").textContent).toMatch(/Terminez d'abord la configuration/);
  });

  it("shows the server's refusal when the message changed meanwhile", async () => {
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: "template_changed", message: "Le message a changé depuis l'approbation : relisez-le puis approuvez à nouveau." } } } });
    await show("/app/journey?id=J1");
    await click(byId("approve-open"));
    await click(byId("approve-confirm"));
    expect(byId("journey-error").textContent).toMatch(/Le message a changé/);
  });

  it("a stale approval is not shown as valid", async () => {
    table["/journeys/J1"] = { data: SUMMARY({ approval: { approved: true, valid: false, reasons: [{ code: "template_changed", label: "Le message a changé depuis l'approbation." }], template_version: 1 } }) };
    await show("/app/journey?id=J1");
    expect(byId("approval-state").textContent).toMatch(/Le message a changé depuis l'approbation/);
    expect(byId("approval-state").className).toMatch(/chip-warn/);
  });

  it("a member can read but not approve or edit", async () => {
    global.__user = member;
    await show("/app/journey?id=J1");
    expect(byId("approve-open").disabled).toBe(true);
    expect(byId("approve-block").textContent).toMatch(/propriétaire ou un administrateur/);
    expect(byId("template-subject").disabled).toBe(true);
    expect(byId("template-save")).toBeNull();
  });
});

describe("the message", () => {
  it("is saved as typed, and says the earlier approval no longer covers a changed wording", async () => {
    api.put.mockResolvedValue({ data: { data: { version: 3, changed: true } } });
    await show("/app/journey?id=J1");
    expect(byId("template-save").disabled).toBe(true);
    await type(byId("template-subject"), "Une question sur {{nom}}");
    expect(byId("template-dirty")).not.toBeNull();
    await click(byId("template-save"));
    expect(api.put).toHaveBeenCalledWith("/journeys/J1/template", { subject: "Une question sur {{nom}}", body: "Bonjour,\n\n{{constat}}\n\n{{offre}}" });
    expect(toast.success.mock.calls[0][0]).toMatch(/version 3.*ne le couvre plus/);
  });
  it("lists the problems the server found and offers the merge fields", async () => {
    table["/journeys/J1"] = { data: SUMMARY({ template: { ...SUMMARY().template, problems: [{ code: "missing_required", label: "Le message doit nommer l'établissement : {{nom}} est absent" }] }, examples: [] }) };
    await show("/app/journey?id=J1");
    expect(byId("template-problems").textContent).toMatch(/{{nom}} est absent/);
    expect(byId("insert-nom")).not.toBeNull();
    expect(byId("examples-none").textContent).toMatch(/pas d'exemple à inventer/);
    expect(byId("approve-block").textContent).toMatch(/Corrigez le message/);
  });
});

describe("the follow-up", () => {
  it("shows progress, what needs the person and the replies, and never says delivered", async () => {
    table["/journeys/J1/progress"] = { data: PROGRESS({ status: "running", total: 12, done: 5, percent: 42, states: { scheduled: 7, accepted: 4, replied: 1 }, actions: [{ code: "unknown_outcome", count: 1, label: "Résultat inconnu : vérifiez la boîte d'envoi (jamais renvoyés d'eux-mêmes)." }], approval_valid: true }) };
    await show("/app/journey?id=J1");
    expect(byId("progress-line").textContent).toMatch(/5 sur 12 traités \(42 %\)/);
    expect(byId("state-accepted").textContent).toMatch(/4 · Acceptés par le serveur SMTP/);
    expect(byId("progress-actions").textContent).toMatch(/jamais renvoyés d'eux-mêmes/);
    expect(byId("journey-progress").textContent).not.toMatch(/livré|delivered/i);
  });
  it("pauses, and withdrawing the approval needs a confirmation", async () => {
    table["/journeys/J1/progress"] = { data: PROGRESS({ status: "running", total: 12, done: 0, percent: 0, states: { scheduled: 12 }, approval_valid: true }) };
    api.post.mockResolvedValue({ data: { data: { status: "paused", cancelled: 12 } } });
    await show("/app/journey?id=J1");
    await click(byId("journey-pause"));
    expect(api.post).toHaveBeenCalledWith("/journeys/J1/pause");
    await click(byId("journey-revoke-open"));
    expect(api.post).toHaveBeenCalledTimes(1); // the confirmation sent nothing
    await click(byId("journey-revoke-confirm"));
    expect(api.post).toHaveBeenLastCalledWith("/journeys/J1/revoke", { reason: "Retirée depuis l'écran de la campagne" });
  });
  it("resume is closed when the approval no longer covers the campaign", async () => {
    table["/journeys/J1/progress"] = { data: PROGRESS({ status: "paused", paused: true, total: 12, done: 0, percent: 0, states: { scheduled: 12 }, approval_valid: false }) };
    await show("/app/journey?id=J1");
    expect(byId("journey-resume").disabled).toBe(true);
  });
});
