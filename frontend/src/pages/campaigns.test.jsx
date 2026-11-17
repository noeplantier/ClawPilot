// Séquences, sans réseau : rangées par statut, une action décisive, rien ne part sans confirmation, le brouillon créé s'ouvre.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() } }));
jest.mock("@/components/CampaignDetailDrawer", () => function Drawer({ open, campaignId }) { return open ? <div data-testid="drawer">{campaignId}</div> : null; });

import { api } from "@/lib/api";
import { clear } from "@/lib/swr";
import Campaigns from "@/pages/Campaigns";

global.IS_REACT_ACT_ENVIRONMENT = true;

const STEP = { id: "s1", channel: "email", delay_hours: 0, subject: "Objet", body: "Bonjour", language: "fr" };
let rows;
const SUGGESTION = { id: "new_leads", kind: "new_leads", title: "Nouveaux", rationale: "r", angle: null, examples: ["A"], eligible: 2, total: 2, hot: 1, avg_heat: 82, pending_review: 0, blocked_reason: null };

let container;
let root;
beforeEach(() => {
  clear();
  rows = [
    { id: "c1", name: "Vide", status: "draft", steps: [], lead_ids: ["l1"], channels: ["email"], sent: 0 },
    { id: "c3", name: "Prête", status: "draft", steps: [STEP], lead_ids: ["l1", "l2"], channels: ["email"], sent: 0 },
    { id: "c4", name: "Active", status: "running", steps: [STEP, STEP], lead_ids: ["l1", "l2"], channels: ["email"], sent: 1, replied: 1 },
  ];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.post, api.patch].forEach((m) => m.mockReset());
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/campaigns/suggestions" ? { basis: { prospects: 0, leads: 2 }, items: [SUGGESTION] } : rows }));
  api.post.mockResolvedValue({ data: { dispatched: 2, not_attempted: 0 } });
  api.patch.mockResolvedValue({ data: {} });
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show(path = "/app/campaigns") {
  await act(async () => { root.render(<MemoryRouter initialEntries={[path]}><Campaigns embedded /></MemoryRouter>); });
  await act(async () => {});
  await act(async () => {});
}
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

test("campaigns are grouped by status, with real progress and one decisive action each", async () => {
  await show();
  expect(q("campaigns-group-draft").textContent).toContain("Brouillons");
  expect(q("campaigns-group-running").textContent).toContain("Active");
  expect(q("campaigns-group-paused")).toBeNull();
  expect(q("next-c1").getAttribute("data-action")).toBe("edit");
  expect(q("next-c3").getAttribute("data-action")).toBe("launch");
  expect(q("next-c4").getAttribute("data-action")).toBe("pause");
  expect(q("campaign-card-c4").textContent).toContain("1 accepté par le fournisseur sur 4 messages prévus");
  expect(document.body.textContent).not.toMatch(/livré|delivered|Book 25|APAC/);
});

test("nothing leaves without a confirmation that states the gates; cancel sends nothing", async () => {
  await show();
  await act(async () => q("next-c3").click());
  expect(q("confirm-send").textContent).toContain("2 destinataires");
  expect(q("confirm-send").textContent).toContain("aucune copie (CC/CCI)");
  await act(async () => q("confirm-send-cancel").click());
  expect(api.post).not.toHaveBeenCalled();
  await act(async () => q("next-c3").click());
  await act(async () => q("confirm-send-go").click());
  expect(api.post).toHaveBeenCalledWith("/campaigns/c3/launch");
});

test("a deep link opens the draft itself, and saving it edits that draft instead of creating another", async () => {
  await show("/app/campaigns?campaign=c1");
  expect(q("builder-title").textContent).toBe("Vide");
  expect(q("builder-note").textContent).toContain("1 destinataire assigné");
  await act(async () => {
    const body = q("step-body-0");
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(body, "Bonjour {{first_name}}");
    body.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => q("save-campaign-button").click());
  expect(api.patch).toHaveBeenCalledWith("/campaigns/c1", expect.objectContaining({ name: "Vide" }));
  expect(api.post).not.toHaveBeenCalledWith("/campaigns", expect.anything());
});

test("creating a draft from a suggestion opens that draft at once; a heat ranking is never called hot", async () => {
  await show();
  expect(q("suggestion-high-score").textContent).toBe("1 score élevé");
  expect(q("suggestions").textContent).not.toMatch(/\bhot\b/i);
  api.post.mockResolvedValueOnce({ data: { campaign_id: "c9", name: "Nouveaux", assigned: 2, left_out: 0 } });
  rows = [...rows, { id: "c9", name: "Nouveaux", status: "draft", steps: [], lead_ids: ["a", "b"], channels: ["email"], sent: 0 }];
  await act(async () => q("suggestion-create").click());
  await act(async () => {});
  await act(async () => {});
  expect(api.post).toHaveBeenCalledWith("/campaigns/suggestions/new_leads/create");
  expect(q("builder-title").textContent).toBe("Nouveaux");
});
