// « Utilisation », sans réseau : les fenêtres et les modèles viennent de l'API mockée, un propriétaire change le modèle,
// un membre le lit seulement. Aucun chiffre inventé.
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

import { api } from "@/lib/api";
import { clear } from "@/lib/swr";
import UsageDialog from "@/components/usage/UsageDialog";

global.IS_REACT_ACT_ENVIRONMENT = true;

const STATE = (model = "equilibre") => ({
  model,
  models: [
    { id: "gabarit", name: "Plantiers Gabarit", tagline: "sans IA", credits: 0, uses_ai: false, default: false },
    { id: "equilibre", name: "Plantiers Équilibre", tagline: "recommandé", credits: 2, uses_ai: true, default: true },
  ],
  windows: [
    { key: "session", label: "Session (5 h)", limit: 30, used: 12, remaining: 18, resets_at: "2099-01-01T10:00:00Z" },
    { key: "day", label: "Aujourd'hui", limit: 100, used: 12, remaining: 88, resets_at: "2099-01-01T23:00:00Z" },
  ],
  settings: ["CREDITS_PER_DAY", "CREDITS_PER_SESSION"],
});

let container;
let root;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  api.put.mockReset();
  api.get.mockResolvedValue({ data: STATE() });
  api.put.mockResolvedValue({ data: STATE("gabarit") });
  global.__user = { id: "u1", role: "owner" };
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show() {
  await act(async () => { root.render(<UsageDialog open onOpenChange={() => {}} />); });
  await act(async () => {});
}
const byId = (id) => document.querySelector(`[data-testid="${id}"]`);

test("shows both windows and the models as the server counted them", async () => {
  await show();
  expect(byId("usage-session-label").textContent).toBe("12 / 30 crédits");
  expect(byId("usage-day-label").textContent).toBe("12 / 100 crédits");
  expect(byId("usage-session").querySelector('[role="progressbar"]').getAttribute("aria-valuenow")).toBe("40");
  expect(byId("model-equilibre").getAttribute("aria-checked")).toBe("true");
  expect(byId("model-equilibre").textContent).toContain("9 messages possibles maintenant"); // 18 credits left in the session / 2
  expect(byId("model-gabarit").textContent).toContain("0 crédit · sans IA");
});

test("an owner chooses a model on the server", async () => {
  await show();
  await act(async () => { byId("model-gabarit").click(); });
  expect(api.put).toHaveBeenCalledWith("/usage/model", { model: "gabarit" });
});

test("a member reads the models but cannot change them", async () => {
  global.__user = { id: "u2", role: "member" };
  await show();
  expect(byId("model-gabarit").disabled).toBe(true);
  expect(document.body.textContent).toContain("Seul un propriétaire ou un administrateur change le modèle.");
});
