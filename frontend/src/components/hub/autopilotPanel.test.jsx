// « Pilote automatique », sans réseau : désactivé par défaut, activable par un propriétaire seulement après les quatre
// confirmations, lancé à la demande ; les interrupteurs serveur manquants sont nommés.
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import { clear } from "@/lib/swr";
import AutopilotPanel from "@/components/hub/AutopilotPanel";

global.IS_REACT_ACT_ENVIRONMENT = true;

const ACKS = ["b2b_use", "auto_approve", "ai_credits", "can_stop"];
const STATE = (over = {}) => ({
  enabled: false, zone: null, search_every_hours: 24, max_approvals: 50, drafts: true, last_run_at: null, next_search_at: null,
  acknowledgements: ACKS, limits: { min_search_hours: 6, max_approvals: 200 }, categories: ["bakeries"],
  requirements: { external_sources: false, prospect_import: true, automation_max: true, live_sending: false }, ...over,
});
const JOB = { id: "j1", status: "succeeded", south: 45.75, west: 4.82, north: 45.77, east: 4.86, category: "bakeries" };

let container;
let root;
let table;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  [api.get, api.put, api.post].forEach((m) => m.mockReset());
  global.__user = { id: "u1", role: "owner" };
  table = { "/autopilot": STATE(), "/map/search": [JOB] };
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(url))));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show() {
  await act(async () => { root.render(<AutopilotPanel />); });
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

test("off by default; the missing server switches are named", async () => {
  await show();
  expect(byId("autopilot-state").textContent).toBe("Désactivé");
  expect(byId("autopilot-missing").textContent).toContain("FEATURE_EXTERNAL_SOURCES=true");
  expect(byId("autopilot-missing").textContent).toContain("FEATURE_LIVE_SENDING=true");
  expect(byId("autopilot-form-zone").textContent).toContain("45.750–45.770° N"); // the zone of the last map search
});

test("an owner turns it on only after the four confirmations, with the zone of the last search", async () => {
  api.put.mockResolvedValue({ data: STATE({ enabled: true, zone: JOB }) });
  await show();
  expect(byId("autopilot-enable").disabled).toBe(true);
  for (const code of ACKS) await act(async () => { byId(`autopilot-ack-${code}`).click(); });
  expect(byId("autopilot-enable").disabled).toBe(false);
  await act(async () => { byId("autopilot-enable").click(); });
  expect(api.put).toHaveBeenCalledWith("/autopilot", expect.objectContaining({
    acknowledgements: ACKS, zone: { south: 45.75, west: 4.82, north: 45.77, east: 4.86, category: "bakeries" }, max_approvals: 50,
  }));
});

test("once on, it runs on demand and says what it did, and nothing was sent", async () => {
  table["/autopilot"] = STATE({ enabled: true, zone: JOB });
  api.post.mockResolvedValue({ data: { ...STATE({ enabled: true }), run: { approval: { approved: 4 }, drafts: { ready: 4 } } } });
  await show();
  await act(async () => { byId("autopilot-run").click(); });
  expect(api.post).toHaveBeenCalledWith("/autopilot/run");
  expect(byId("autopilot-last-run").textContent).toBe("4 prospect(s) approuvé(s) · 4 brouillon(s) prêt(s). Rien n'a été envoyé par le pilote.");
});

test("an admin cannot turn it on", async () => {
  global.__user = { id: "u2", role: "admin" };
  await show();
  expect(byId("autopilot-form")).toBeNull();
  expect(container.textContent).toContain("Seul un propriétaire peut activer le pilote automatique.");
});
