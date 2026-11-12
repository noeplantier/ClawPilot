// « Automatisation max », sans navigateur ni réseau. Ce que ces tests figent : le mode est désactivé par défaut et l'écran le dit
// (sans pouvoir l'activer) ; un mandat se crée en brouillon et n'agit pas ; l'activation exige les quatre confirmations explicites
// et un propriétaire ; la pause et la révocation sont atteignables ; le rapport et le journal sont lisibles.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import { clear } from "@/lib/swr";
import AutomationMax from "@/pages/AutomationMax";

global.IS_REACT_ACT_ENVIRONMENT = true;

const owner = { id: "u1", role: "owner", email: "o@x.example" };
const admin = { id: "u3", role: "admin", email: "a@x.example" };
const member = { id: "u2", role: "member", email: "m@x.example" };
const ZONE = { kind: "bbox", south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant", label: null };
const ACKS = ["bounded", "real_sending", "provider_terms", "can_revoke"];
const STOP_LABELS = { kill_switch: "Arrêt d'urgence actif (SEND_KILL_SWITCH)", bounce_rate: "Trop de rebonds : l'envoi est suspendu" };
const MANDATE = (over = {}) => ({
  id: "M1", name: "Mandat · Lyon 6", status: "draft", campaign_id: "J1", zones: [ZONE], template_version: 2, daily_cap: 20, total_cap: 60, ai_budget: 0,
  window: [8, 18], min_delay_seconds: 60, search_every_hours: 24, expires_at: "2026-11-25T10:00:00Z", stop_rules: { max_bounce_rate: 0.05, max_opt_out_rate: 0.1, min_sample: 20 },
  provider: "smtp_hostinger", activated_at: null, last_run_at: null, ended_at: null, ended_reason: null, ended_label: null, created_at: "2026-11-11T10:00:00Z", ...over,
});
const OVERVIEW = (over = {}) => ({
  enabled: true, flag: "FEATURE_AUTOMATION_MAX", why_disabled: null, stop_labels: STOP_LABELS, reply_collection_configured: true, acknowledgements: ACKS,
  limits: { max_daily: 50, max_total: 100, max_days: 30, zones: 1, min_delay_seconds: 30, min_search_hours: 6 }, defaults: {}, mandates: [], ...over,
});

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
  table = { "/mandates": { data: OVERVIEW() }, "/journeys": { items: [{ id: "J1", name: "Lyon 6", status: "running", zone: ZONE, recipients: 12, planned: 0, sent: 0, created_at: "2026-11-10T08:00:00Z" }] } };
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(`unexpected GET ${url}`))));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show() {
  await act(async () => { root.render(<MemoryRouter><AutomationMax /></MemoryRouter>); });
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const text = () => container.textContent;
const click = async (el) => { await act(async () => { el.click(); }); await act(async () => {}); };

describe("off by default", () => {
  beforeEach(() => { table["/mandates"] = { data: OVERVIEW({ enabled: false, why_disabled: "Le mode automatique est désactivé sur ce serveur (FEATURE_AUTOMATION_MAX)" }) }; });

  it("says it is disabled on this server and that only the server's operator can turn it on", async () => {
    await show();
    expect(byId("max-switch-state").textContent).toBe("Désactivé sur ce serveur");
    expect(byId("max-switch").textContent).toMatch(/FEATURE_AUTOMATION_MAX/);
    expect(byId("max-switch").textContent).toMatch(/décision de l'opérateur du serveur/);
  });
  it("offers no form to create a mandate and does nothing on its own", async () => {
    await show();
    expect(byId("mandate-form")).toBeNull();
    expect(byId("max-empty")).not.toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });
  it("an existing mandate cannot be activated while the mode is off, but can still be revoked", async () => {
    table["/mandates"] = { data: OVERVIEW({ enabled: false, why_disabled: "Le mode automatique est désactivé sur ce serveur (FEATURE_AUTOMATION_MAX)", mandates: [MANDATE({ status: "active" })] }) };
    api.post.mockResolvedValue({ data: { data: MANDATE({ status: "revoked" }) } });
    await show();
    expect(byId("mandate-authorisation")).toBeNull(); // an active mandate has nothing left to authorise
    await click(byId("mandate-revoke-open"));
    await click(byId("mandate-revoke-confirm"));
    expect(api.post).toHaveBeenCalledWith("/mandates/M1/revoke");
  });
});

describe("creating a mandate", () => {
  it("starts with careful bounds, no AI budget, and creates a draft without activating it", async () => {
    api.post.mockResolvedValue({ data: { data: MANDATE() } });
    await show();
    expect(byId("mandate-ai_budget").value).toBe("0");
    expect(byId("mandate-daily_cap").value).toBe("20");
    expect(text()).toMatch(/Arrêts fixes, non désactivables/);
    await click(byId("mandate-create"));
    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe("/mandates");
    expect(body).toMatchObject({ campaign_id: "J1", daily_cap: 20, total_cap: 100, days: 14, ai_budget: 0, stop_rules: { max_bounce_rate: 0.05, max_opt_out_rate: 0.1, min_sample: 20 } });
    expect(api.post.mock.calls.some(([u]) => /activate/.test(u))).toBe(false);
    expect(toast.success.mock.calls[0][0]).toMatch(/n'agit pas encore/);
  });
  it("sends nothing when a bound is outside what the server allows, and says which", async () => {
    await show();
    const input = byId("mandate-daily_cap");
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value").set;
    await act(async () => { setter.call(input, "500"); input.dispatchEvent(new Event("input", { bubbles: true })); });
    await click(byId("mandate-create"));
    expect(api.post).not.toHaveBeenCalled();
    expect(text()).toMatch(/Plafond par jour : un entier de 1 à 50/);
  });
  it("asks for a campaign by zone first when there is none", async () => {
    table["/journeys"] = { items: [] };
    await show();
    expect(byId("mandate-no-journey")).not.toBeNull();
  });
});

describe("the explicit authorisation", () => {
  beforeEach(() => { table["/mandates"] = { data: OVERVIEW({ mandates: [MANDATE()] }) }; });

  it("shows the terms of the mandate, then keeps activation closed until the four confirmations are ticked", async () => {
    await show();
    expect(byId("mandate-status").textContent).toMatch(/Brouillon : rien n'agit encore/);
    expect(byId("mandate-terms").textContent).toMatch(/20 par jour, 60 au total/);
    expect(byId("mandate-terms").textContent).toMatch(/sans IA/);
    expect(byId("mandate-activate").disabled).toBe(true);
    expect(byId("activate-block").textContent).toMatch(/4 confirmations restantes/);
    for (const code of ACKS.slice(0, 3)) await click(byId(`ack-${code}`));
    expect(byId("activate-block").textContent).toMatch(/1 confirmation restante/);
    expect(byId("mandate-activate").disabled).toBe(true);
    expect(api.post).not.toHaveBeenCalled();
  });
  it("sends the four codes, once everything is ticked", async () => {
    api.post.mockResolvedValue({ data: { data: MANDATE({ status: "active" }) } });
    await show();
    for (const code of ACKS) await click(byId(`ack-${code}`));
    expect(byId("mandate-activate").disabled).toBe(false);
    await click(byId("mandate-activate"));
    expect(api.post).toHaveBeenCalledWith("/mandates/M1/activate", { acknowledgements: ACKS });
  });
  it("only an owner can give it, an admin can still pause and revoke", async () => {
    global.__user = admin;
    await show();
    expect(byId("mandate-activate").disabled).toBe(true);
    expect(byId("activate-block").textContent).toMatch(/Seul un propriétaire/);
    expect(byId("mandate-revoke-open")).not.toBeNull();
  });
  it("is closed while the replies are not read, whatever is ticked", async () => {
    table["/mandates"] = { data: OVERVIEW({ reply_collection_configured: false, mandates: [MANDATE()] }) };
    await show();
    for (const code of ACKS) await click(byId(`ack-${code}`));
    expect(byId("mandate-activate").disabled).toBe(true);
    expect(byId("activate-block").textContent).toMatch(/IMAP/);
  });
  it("a member sees the mandate but has no authorisation form and no control", async () => {
    global.__user = member;
    await show();
    expect(byId("mandate-card")).not.toBeNull();
    expect(byId("mandate-authorisation")).toBeNull();
    expect(byId("mandate-revoke-open")).toBeNull();
    expect(byId("mandate-form")).toBeNull();
  });
  it("shows the server's refusal sentence", async () => {
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: "not_ready", message: "Le message de la campagne n'est pas approuvé." } } } });
    await show();
    for (const code of ACKS) await click(byId(`ack-${code}`));
    await click(byId("mandate-activate"));
    expect(byId("max-error").textContent).toBe("Le message de la campagne n'est pas approuvé.");
  });
});

describe("pause, revocation and the report", () => {
  beforeEach(() => { table["/mandates"] = { data: OVERVIEW({ mandates: [MANDATE({ status: "active", activated_at: "2026-11-11T10:00:00Z" })] }) }; });

  it("pauses at once and revokes only after a confirmation that says it is final", async () => {
    api.post.mockResolvedValue({ data: { data: MANDATE({ status: "suspended" }) } });
    await show();
    await click(byId("mandate-suspend"));
    expect(api.post).toHaveBeenCalledWith("/mandates/M1/suspend");
    await click(byId("mandate-revoke-open"));
    expect(text()).toMatch(/Immédiat et définitif/);
    expect(api.post).toHaveBeenCalledTimes(1);
    await click(byId("mandate-revoke-confirm"));
    expect(api.post).toHaveBeenLastCalledWith("/mandates/M1/revoke");
  });
  it("reads the compact report and the journal with the reasons in words", async () => {
    table["/mandates/M1/report"] = { data: {
      mandate: MANDATE({ status: "active" }), last_24h: { sent: 3 }, total: { sent: 9 }, remaining: { messages: 51, days: 13 },
      note: "Ce mode n'a rien élargi : zone, offre, modèle, expéditeur, plafonds et budget sont ceux de l'autorisation.",
      journal: [
        { at: "2026-11-11T11:00:00Z", action: "held", actor: "system", detail: { reason: "kill_switch" } },
        { at: "2026-11-11T10:00:00Z", action: "activated", actor: "user", detail: {} },
      ],
    } };
    await show();
    await click(byId("mandate-report-open"));
    expect(byId("mandate-report").textContent).toMatch(/Dernières 24 h : 3 envoyés\. Au total : 9\. Il reste 51 messages et 13 jours/);
    expect(byId("mandate-report").textContent).toMatch(/n'a rien élargi/);
    expect(byId("mandate-journal").textContent).toMatch(/Rien envoyé ce tour-ci : Arrêt d'urgence actif \(SEND_KILL_SWITCH\) · automatique/);
    expect(byId("mandate-journal").textContent).toMatch(/Autorisation donnée .* par une personne/);
  });
  it("shows why a mandate ended", async () => {
    table["/mandates"] = { data: OVERVIEW({ mandates: [MANDATE({ status: "suspended", ended_reason: "bounce_rate", ended_label: "Trop de rebonds : l'envoi est suspendu" })] }) };
    await show();
    expect(byId("mandate-ended").textContent).toMatch(/Trop de rebonds/);
  });
});
