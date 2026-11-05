// Render tests for « Campagne individuelle », without a browser and without any network: the API module is mocked.
// What they pin down: nothing is generated, planned or sent by merely opening the screen; the provider's restriction is
// shown; the final button carries its label, asks for confirmation and sends the number that was read; the review shows the
// evidence and the blockers; the tracking never says "delivered".
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import { clear } from "@/lib/swr";
import Launch from "@/pages/Launch";

global.IS_REACT_ACT_ENVIRONMENT = true;

const owner = { id: "u1", role: "owner", email: "o@x.example" };
const member = { id: "u2", role: "member", email: "m@x.example" };

const GATES = {
  provider: { id: "smtp_hostinger", label: "SMTP Hostinger (smtp.hostinger.com)", host: "smtp.hostinger.com", cold_outreach: "opt_in_required", restriction: "Messagerie mutualisée Hostinger : opt-in explicite requis." },
  dry_run: true, live: false, kill_switch: false, paused: false, sandbox: true, allowlist_size: 0, sender_configured: true, smtp_complete: true,
  max_per_day: 20, max_per_hour: 100, min_delay_seconds: 60, window_start_hour: 8, window_end_hour: 18, timezone: "Europe/Paris", timezone_source: "lead_country",
  sent_today: 0, sent_last_hour: 0, next_allowed_at: null, scheduler: { checked: true, worker_ok: true, beat_ok: true },
};
const LAUNCH = { id: "L1", name: "Lot de test", status: "draft", created_at: "2030-06-01T08:00:00Z", recipients: 100, planned: 0, sent: 0 };
const PLAN = (over = {}) => ({
  selected: 100, sendable: 96, stages: { ready: 96, excluded: 4 }, exclusions: { suppressed: 3, bounced: 1 },
  exclusion_labels: { suppressed: "Sur la liste de suppression", bounced: "Rebond bloquant" },
  schedule: { first_at: "2030-06-03T07:00:00Z", last_at: "2030-06-07T15:30:00Z", timezone: "Europe/Paris", days: [{ date: "2030-06-03", count: 20 }] },
  blockers: [], warnings: [{ code: "dry_run", label: "Envoi réel désactivé (dry-run) : les messages seront simulés, rien ne partira" }],
  gates: GATES, generated_at: "2030-06-01T08:00:00Z",
  ...over,
});
const ROW = (over = {}) => ({
  lead_id: "p1", name: "Bistro 001", city: "Lyon", email: "bistro001@restaurant-test.fr", stage: "to_review", exclusion: null,
  draft: { id: "d1", status: "draft", subject: "À propos de Bistro 001", body: "Bonjour,\n\nJe me permets de vous écrire au sujet de Bistro 001 (Lyon).", edited: false, auto: true, created_at: "2030-06-01T08:00:00Z" },
  draft_job: null,
  evidence: { facts: ["Votre établissement ne semble pas disposer d'un site web propre dans l'annuaire."], site_state: "none_identified", source: { name: "osm", url: "https://www.openstreetmap.org/node/1", fetched_at: "2030-05-30T08:00:00Z" } },
  authorization: { ok: true, basis: "opt_in", code: null, label: "Autorisé : opt-in explicite enregistré" },
  problems: [], dispatch: null,
  ...over,
});
const OVERVIEW = (over = {}) => ({
  launch: LAUNCH, stages: { to_review: 2, ready: 96, excluded: 2 }, exclusions: { suppressed: 2 }, exclusion_labels: { suppressed: "Sur la liste de suppression" },
  dispatch: {}, draft_jobs: {}, gates: GATES, ...over,
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
  global.__user = owner;
  Object.values(toast).forEach((m) => m.mockReset());
  table = {
    "/launches/provider": GATES,
    "/launches": [LAUNCH],
    "/launches/L1": OVERVIEW(),
    "/launches/L1/review": { total: 2, items: [ROW(), ROW({ lead_id: "p2", name: "Bistro 002", draft: { ...ROW().draft, id: "d2", subject: "À propos de Bistro 002" }, problems: [{ code: "unresolved_variable", label: "Variable non résolue : {{prenom}}", blocking: true }], authorization: { ok: false, basis: "public_directory", code: "provider_requires_opt_in", label: "Non autorisé via SMTP Hostinger : annuaire public, aucun opt-in enregistré" } })] },
    "/launches/L1/plan": PLAN(),
    "/launches/L1/tracking": { counts: {}, labels: {}, total: 0, items: [] },
  };
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(`unexpected GET ${url}`))));
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function show(path = "/app/launch") {
  await act(async () => {
    root.render(<MemoryRouter initialEntries={[path]}><Launch /></MemoryRouter>);
  });
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const all = (id) => [...container.querySelectorAll(`[data-testid="${id}"]`)];
const text = () => container.textContent;
const click = async (el) => {
  await act(async () => { el.click(); });
  await act(async () => {});
};

describe("Campagne individuelle", () => {
  it("shows the provider, its restriction and the guard-rails, and does nothing by itself on opening", async () => {
    await show();
    expect(byId("launch-provider-chip").textContent).toMatch(/Hostinger.*Opt-in explicite requis/);
    expect(byId("launch-provider-restriction").textContent).toMatch(/opt-in explicite requis/);
    expect(text()).toMatch(/quota d'envoi disponible ne vaut pas autorisation/);
    expect(byId("launch-gates").textContent).toMatch(/Simulation \(dry-run\)/);
    expect(byId("launch-limits").textContent).toMatch(/20 par jour/);
    expect(byId("launch-scheduler").textContent).toMatch(/Worker et beat détectés/);
    expect(api.post).not.toHaveBeenCalled(); // nothing generated, planned or sent by rendering
    expect(api.put).not.toHaveBeenCalled();
  });

  it("creates a selection of 100 on demand, with the name and the size typed", async () => {
    await show();
    expect(byId("launch-create-submit").textContent).toMatch(/SÉLECTIONNER 100 ÉTABLISSEMENTS/);
    api.post.mockResolvedValue({ data: { launch: LAUNCH, requested: 100, selected: 96, scanned: 130, not_approved: 4, excluded: [] } });
    await click(byId("launch-create-submit"));
    expect(api.post).toHaveBeenCalledWith("/launches", { name: "Campagne individuelle", size: 100 });
    expect(toast.success).toHaveBeenCalledWith("96 établissement(s) sélectionné(s) sur 100 demandé(s).");
  });

  it("a member cannot create a selection", async () => {
    global.__user = member;
    await show();
    expect(byId("launch-create-submit")).toBeNull();
    expect(text()).toMatch(/Seuls un propriétaire ou un administrateur/);
  });

  it("shows the review with recipient, subject, body, evidence, channel authorization and blockers", async () => {
    await show("/app/launch?id=L1");
    const rows = all("launch-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Bistro 001");
    expect(rows[0].querySelector('[data-testid="launch-row-email"]').textContent).toBe("bistro001@restaurant-test.fr");
    expect(rows[0].querySelector('[data-testid="launch-row-subject"]').textContent).toBe("À propos de Bistro 001");
    expect(rows[0].querySelector('[data-testid="launch-row-body"]').textContent).toMatch(/Je me permets de vous écrire au sujet de Bistro 001/);
    expect(rows[0].querySelector('[data-testid="launch-row-evidence"]').textContent).toMatch(/Aucun site identifié après recherche/);
    expect(rows[0].querySelector('[data-testid="launch-row-evidence"]').textContent).toMatch(/source osm/);
    expect(rows[0].querySelector('[data-testid="launch-row-auth"]').textContent).toBe("Opt-in enregistré");
    expect(rows[1].querySelector('[data-testid="launch-row-auth"]').textContent).toBe("Canal non autorisé");
    expect(rows[1].querySelector('[data-testid="launch-row-problems"]').textContent).toMatch(/Bloque : Variable non résolue : \{\{prenom\}\}/);
    // only the clean draft can be picked
    expect(all("launch-row-check")).toHaveLength(1);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("approves the picked drafts only, then says what was done", async () => {
    await show("/app/launch?id=L1");
    expect(byId("launch-approve").disabled).toBe(true);
    await click(byId("launch-select-all"));
    expect(byId("launch-approve").textContent).toMatch(/\(1\)/);
    api.post.mockResolvedValue({ data: { results: [{ draft_id: "d1", ok: true, reason: null }], done: 1, refused: 0 } });
    await click(byId("launch-approve"));
    expect(api.post).toHaveBeenCalledWith("/launches/L1/review-drafts", { draft_ids: ["d1"], decision: "approve" });
    expect(toast.success).toHaveBeenCalledWith("1 brouillon approuvé.");
  });

  it("an empty draft state is explicit, and generation is a button, never a render side effect", async () => {
    table["/launches/L1"] = OVERVIEW({ stages: { no_draft: 5 }, draft_jobs: { queued: 3, unavailable: 2 } });
    await show("/app/launch?id=L1");
    expect(byId("launch-jobs").textContent).toMatch(/3 en file · 2 en attente de l'IA/);
    expect(api.post).not.toHaveBeenCalled();
    expect(byId("launch-generate").textContent).toMatch(/GÉNÉRER LES BROUILLONS MANQUANTS \(5\)/);
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: "Describe your offer first" } } });
    await click(byId("launch-generate"));
    expect(api.post).toHaveBeenCalledWith("/launches/L1/drafts");
    expect(byId("launch-drafts-notice").textContent).toMatch(/Describe your offer first/);
  });

  it("shows the really sendable count, the exclusions and the schedule before the final button", async () => {
    await show("/app/launch?id=L1");
    expect(byId("launch-sendable").textContent).toBe("96");
    expect(byId("launch-exclusions").textContent).toMatch(/3 · Sur la liste de suppression/);
    expect(byId("launch-exclusions").textContent).toMatch(/1 · Rebond bloquant/);
    expect(byId("launch-schedule-line").textContent).toMatch(/\(heures : Europe\/Paris\)/);
    expect(byId("launch-warning").textContent).toMatch(/dry-run/);
    expect(byId("launch-schedule").textContent.trim()).toBe("Planifier les messages approuvés");
    expect(byId("launch-schedule").disabled).toBe(false);
  });

  it("the final button asks for confirmation, then sends the number it read; nothing is sent from the screen", async () => {
    await show("/app/launch?id=L1");
    await click(byId("launch-schedule"));
    expect(api.post).not.toHaveBeenCalled(); // the first click only asks
    expect(byId("launch-confirm-text").textContent).toMatch(/Planifier 96 messages.*sans copie ni copie cachée.*Rien ne part maintenant/);
    api.post.mockResolvedValue({ data: PLAN({ scheduled: 96 }) });
    await click(byId("launch-confirm-yes"));
    expect(api.post).toHaveBeenCalledWith("/launches/L1/schedule", { expected_count: 96 });
    expect(toast.success.mock.calls[0][0]).toMatch(/96 message\(s\) planifié\(s\)\. Rien n'est parti/);
  });

  it("a stale count is refused by the server, and the screen asks for a new reading", async () => {
    await show("/app/launch?id=L1");
    await click(byId("launch-schedule"));
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: { code: "plan_changed", message: "95 messages sont envoyables, pas 96", actual: 95 } } } });
    const reads = api.get.mock.calls.filter(([u]) => u === "/launches/L1/plan").length;
    await click(byId("launch-confirm-yes"));
    expect(toast.error.mock.calls[0][0]).toMatch(/95 messages sont envoyables, pas 96.*relisez-le/);
    expect(api.get.mock.calls.filter(([u]) => u === "/launches/L1/plan").length).toBeGreaterThan(reads);
    expect(byId("launch-confirm")).toBeNull();
  });

  it("is off, with the reason, when nothing is sendable, when something blocks, and for a member", async () => {
    table["/launches/L1/plan"] = PLAN({ sendable: 0, schedule: { first_at: null, last_at: null, timezone: "Europe/Paris", days: [] } });
    await show("/app/launch?id=L1");
    expect(byId("launch-schedule").disabled).toBe(true);
    expect(byId("launch-schedule-reason").textContent).toMatch(/Aucun message approuvé/);
    act(() => root.unmount());
    root = createRoot(container);
    clear();
    table["/launches/L1/plan"] = PLAN({ blockers: [{ code: "sender_not_configured", label: "Identité de l'expéditeur non configurée (OUTREACH_SENDER_*)" }] });
    await show("/app/launch?id=L1");
    expect(byId("launch-schedule").disabled).toBe(true);
    expect(byId("launch-blocker").textContent).toMatch(/OUTREACH_SENDER_/);
    act(() => root.unmount());
    root = createRoot(container);
    clear();
    table["/launches/L1/plan"] = PLAN();
    global.__user = member;
    await show("/app/launch?id=L1");
    expect(byId("launch-schedule").disabled).toBe(true);
    expect(byId("launch-schedule-reason").textContent).toMatch(/propriétaire ou un administrateur/);
    expect(byId("launch-cancel")).toBeNull();
  });

  it("tracks honestly: accepted by SMTP with no proof of delivery, simulated, reply, opposition, never 'delivered'", async () => {
    table["/launches/L1/tracking"] = {
      counts: { accepted: 1, simulated: 1, replied: 1, opted_out: 1, failed: 1 },
      labels: { accepted: "Accepté par SMTP (livraison non prouvée)", simulated: "Simulé (dry-run, rien n'est parti)", replied: "Réponse reçue", opted_out: "Opposition", failed: "Échec" },
      total: 5,
      items: ["accepted", "simulated", "replied", "opted_out", "failed"].map((state, i) => ({
        lead_id: `p${i}`, name: `Bistro ${i}`, city: "Lyon", email: `b${i}@restaurant-test.fr`, state,
        label: { accepted: "Accepté par SMTP (livraison non prouvée)", simulated: "Simulé (dry-run, rien n'est parti)", replied: "Réponse reçue", opted_out: "Opposition", failed: "Échec" }[state],
        reason: null, planned_at: "2030-06-03T07:00:00Z", dispatched_at: "2030-06-03T07:01:00Z", adapter: "smtp", dry_run: false,
      })),
    };
    await show("/app/launch?id=L1");
    const states = all("launch-track-state").map((e) => e.textContent);
    expect(states).toEqual(["Accepté par SMTP (livraison non prouvée)", "Simulé (dry-run, rien n'est parti)", "Réponse reçue", "Opposition", "Échec"]);
    expect(states.some((s) => /^livré/i.test(s))).toBe(false);
    expect(byId("launch-delivery-note").textContent).toMatch(/pas une preuve de livraison/);
    expect(byId("launch-progress").textContent).toMatch(/5 \/ 5 traités/);
  });
});
