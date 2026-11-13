// Les pages fusionnées (Campagnes, À traiter, Automatisations), sans navigateur ni réseau. Ce que ces tests figent : un seul titre,
// des onglets qui sont de vrais chemins, des compteurs et des graphiques lus sur l'API (jamais un 0 inventé), et chaque écran
// d'origine rendu tel quel dans son onglet (ses portes d'envoi ne changent pas).
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", role: "owner" } }) }));
const stub = (name) => ({ __esModule: true, default: ({ embedded }) => <div data-testid={`screen-${name}`}>{embedded ? "embedded" : "standalone"}</div> });
jest.mock("@/pages/Journey", () => stub("journey"));
jest.mock("@/pages/Launch", () => stub("launch"));
jest.mock("@/pages/Campaigns", () => stub("campaigns"));
jest.mock("@/pages/ReviewQueue", () => stub("review"));
jest.mock("@/pages/ToEnrich", () => stub("to-enrich"));
jest.mock("@/pages/Agents", () => stub("agents"));
jest.mock("@/pages/AutomationMax", () => stub("max"));

import { api } from "@/lib/api";
import { clear } from "@/lib/swr";
import CampaignsHub from "@/pages/CampaignsHub";
import QualifyHub from "@/pages/QualifyHub";
import AutomationsHub from "@/pages/AutomationsHub";
import { campaignBars, countOf, liveLine, pulseTiles } from "@/lib/hubFormat";

global.IS_REACT_ACT_ENVIRONMENT = true;

const SERIES = [{ date: "2026-11-12", sent: 3, replied: 1, acquired: 0 }, { date: "2026-11-13", sent: 5, replied: 0, acquired: 2 }];
const OVERVIEW = {
  kpis: { replies: 1, reply_rate: 0.125, bounces: 0, bounce_rate: 0, unsubscribed: 0, messages: 8 },
  limits: { sent_today: 5, max_per_day: 20, remaining_today: 15, sent_last_hour: 2, max_per_hour: 100, min_delay_seconds: 60, dry_run: false, kill_switch: false, paused: false, smtp_configured: true, sandbox: true, allowlist_size: 2 },
  series: SERIES,
  campaigns: [{ id: "c1", name: "Lyon 6", status: "running", sent: 8, opened: 0, replied: 1 }],
};

let container;
let root;
let table;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  table = {
    "/dashboard/overview": OVERVIEW,
    "/journeys": { items: [{ id: "J1" }, { id: "J2" }] },
    "/launches": [{ id: "L1" }],
    "/campaigns": [{ id: "c1" }, { id: "c2" }, { id: "c3" }],
    "/prospects/queues": { total: 7, empty: 0 },
    "/prospects/to-enrich": { total: 12, items: [] },
    "/mandates": { data: { mandates: [{ id: "M1" }] } },
  };
  api.get.mockImplementation((url) => (url in table ? Promise.resolve({ data: table[url] }) : Promise.reject(new Error(`unexpected GET ${url}`))));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function show(node, path) {
  await act(async () => { root.render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>); });
  await act(async () => {});
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

describe("Campagnes: zone, individuelle and séquences on one live page", () => {
  it("draws one title, the three tabs as paths with the counts the API returned, and the screen of the current path", async () => {
    await show(<CampaignsHub tab="launch" />, "/app/launch");
    expect(container.querySelectorAll("h1")).toHaveLength(1);
    expect(byId("hub-tab-journey").getAttribute("href")).toBe("/app/journey");
    expect(byId("hub-tab-journey-count").textContent).toBe("2");
    expect(byId("hub-tab-launch-count").textContent).toBe("1");
    expect(byId("hub-tab-campaigns-count").textContent).toBe("3");
    expect(byId("hub-tab-launch").getAttribute("aria-selected")).toBe("true");
    expect(byId("screen-launch").textContent).toBe("embedded");
    expect(byId("screen-journey")).toBeNull();
  });
  it("shows the live numbers and charts read from the dashboard overview", async () => {
    await show(<CampaignsHub tab="campaigns" />, "/app/campaigns");
    expect(byId("pulse-sent-today-value").textContent).toBe("5 / 20");
    expect(byId("pulse-replies-value").textContent).toBe("1");
    expect(byId("activity-chart")).not.toBeNull();
    expect(byId("pulse-campaigns").textContent).toContain("Lyon 6");
    expect(byId("pulse-live").textContent).toMatch(/En direct · mis à jour à .* · toutes les 10 s/);
    expect(api.get).toHaveBeenCalledWith("/dashboard/overview", { params: { days: 14 } });
  });
  it("a count the API did not give is not drawn, never an invented 0", async () => {
    table["/launches"] = undefined;
    delete table["/launches"];
    await show(<CampaignsHub tab="journey" />, "/app/journey");
    expect(byId("hub-tab-launch-count")).toBeNull();
    expect(byId("screen-journey").textContent).toBe("embedded");
  });
});

describe("À traiter: à vérifier and à enrichir on one page", () => {
  it("counts both queues from the server and opens the asked tab", async () => {
    await show(<QualifyHub tab="to-enrich" />, "/app/prospects/to-enrich");
    expect(byId("hub-tab-review-count").textContent).toBe("7");
    expect(byId("hub-tab-to-enrich-count").textContent).toBe("12");
    expect(byId("hub-tab-to-enrich").getAttribute("aria-selected")).toBe("true");
    expect(byId("screen-to-enrich").textContent).toBe("embedded");
    expect(byId("screen-review")).toBeNull();
  });
});

describe("Automatisations: mandate and agents on one page", () => {
  it("opens the mandate by default and the agents on their path", async () => {
    await show(<AutomationsHub tab="max" />, "/app/automation-max");
    expect(byId("screen-max").textContent).toBe("embedded");
    expect(byId("hub-tab-max-count").textContent).toBe("1");
    await show(<AutomationsHub tab="agents" />, "/app/agents");
    expect(byId("screen-agents").textContent).toBe("embedded");
  });
});

describe("hubFormat", () => {
  it("prints the API's numbers and a dash for a missing rate", () => {
    const tiles = pulseTiles({ ...OVERVIEW, kpis: { ...OVERVIEW.kpis, reply_rate: null } });
    expect(tiles.find((t) => t.key === "replies").hint).toBe("Taux de réponse —");
    expect(pulseTiles(null)).toEqual([]);
  });
  it("sorts the campaigns by what they really sent", () => {
    expect(campaignBars([{ name: "a", sent: 1 }, { name: "b", sent: 9 }, { name: "c" }]).map((b) => b.name)).toEqual(["b", "a"]);
  });
  it("counts a list or a total, else nothing", () => {
    expect(countOf([1, 2])).toBe(2);
    expect(countOf({ total: 4 })).toBe(4);
    expect(countOf(null)).toBeUndefined();
    expect(countOf({ items: [] })).toBeUndefined();
  });
  it("says when the refresh failed", () => {
    expect(liveLine({ updatedAt: null })).toBe("Chargement…");
    expect(liveLine({ updatedAt: new Date(), stale: true, intervalMs: 10000 })).toMatch(/^Rafraîchissement en échec/);
  });
});
