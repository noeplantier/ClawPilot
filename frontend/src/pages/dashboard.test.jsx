/* global MouseEvent */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
let mockUser = { role: "owner" };
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));

import { api } from "@/lib/api";
import Dashboard from "@/pages/Dashboard";

global.IS_REACT_ACT_ENVIRONMENT = true;

const LIMITS = { dry_run: true, kill_switch: false, paused: false, blocked_by: null, max_per_day: 20, max_per_hour: 100, min_delay_seconds: 60, sent_today: 0, remaining_today: 20, sent_last_hour: 0, next_allowed_at: null, sandbox: true, allowlist_size: 0, smtp_configured: false };
const EMPTY = {
  generated_at: "2026-10-03T10:00:00Z",
  kpis: { prospects: 0, pending_review: 0, approved: 0, scored: 0, avg_score: null, sent_today: 0, messages: 0, replies: 0, reply_rate: null, bounces: 0, bounce_rate: null, unsubscribed: 0 },
  series: [{ date: "2026-10-03", sent: 0, replied: 0 }], latest_prospects: [], latest_signals: [], campaigns: [], limits: LIMITS, inbox: [],
};
const FULL = {
  ...EMPTY,
  kpis: { ...EMPTY.kpis, prospects: 3, pending_review: 2, approved: 1, scored: 3, avg_score: 41.5, sent_today: 2, messages: 2, replies: 1, reply_rate: 0.5, bounces: 1, bounce_rate: 0.5 },
  series: [{ date: "2026-10-03", sent: 2, replied: 1 }],
  latest_prospects: [{ id: "p1", name: "La Table d'Alice", city: "Lyon", review_status: "pending", created_at: "2026-10-03T09:00:00Z", score: 55 }],
  latest_signals: [{ lead_id: "p1", name: "La Table d'Alice", key: "no_website", label: "No own website listed", evidence: "No website listed in fixture_directory", observed_at: "2026-10-03T09:00:00Z" }],
  campaigns: [{ id: "c1", name: "Spring", status: "running", sent: 0, opened: 0, replied: 0, open_rate: null, reply_rate: null }],
  inbox: [{ message_id: "m1", lead_id: "p1", name: "La Table d'Alice", excerpt: "Intéressé", simulated: true, at: "2026-10-03T09:30:00Z" }],
  limits: { ...LIMITS, sent_today: 2, remaining_today: 18 },
};

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

async function show(data, role = "owner") {
  mockUser = { role };
  api.get.mockResolvedValue({ data });
  await act(async () => root.render(<MemoryRouter><Dashboard /></MemoryRouter>));
  await act(async () => {});
}

beforeEach(() => { jest.clearAllMocks(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("with no data, every widget shows an explicit empty state and no invented number", async () => {
  await show(EMPTY);
  expect(byId("kpi-avg_score-value").textContent).toBe("—");
  expect(byId("kpi-replies-hint").textContent).toBe("no message sent yet");
  for (const id of ["chart-empty", "signals-empty", "campaigns-empty", "inbox-empty"]) expect(byId(id)).not.toBeNull();
  expect(byId("limits-mode").textContent).toBe("DRY-RUN");
});

test("with data, the widgets show the real figures and link to the prospect", async () => {
  await show(FULL);
  expect(byId("kpi-prospects-value").textContent).toBe("3");
  expect(byId("kpi-avg_score-value").textContent).toBe("41.5");
  expect(byId("kpi-replies-hint").textContent).toBe("50% of 2 sent");
  expect(byId("activity-chart").querySelector("svg").getAttribute("aria-label")).toContain("2 messages sent and 1 reply");
  expect(byId("latest-signals").textContent).toContain("No own website listed");
  expect(byId("campaign-open-rate").textContent).toBe("—"); // nothing sent: unknown, not 0%
  expect(byId("limits-quota").textContent).toBe("2 / 20");
  expect(byId("inbox-item").textContent).toContain("simulated");
  expect(byId("inbox-follow-up").getAttribute("href")).toBe("/app/prospects/p1");
});

test("an owner can pause sending from the dashboard; a member cannot", async () => {
  api.put.mockResolvedValue({ data: {} });
  await show(FULL);
  await act(async () => { byId("limits-toggle-pause").dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  expect(api.put).toHaveBeenCalledWith("/outbound/limits", { sending_paused: true });
  await act(async () => root.unmount());
  root = createRoot(container);
  await show(FULL, "member");
  expect(byId("limits-toggle-pause")).toBeNull();
});

test("a server error shows a retryable error, not placeholder figures", async () => {
  mockUser = { role: "owner" };
  api.get.mockRejectedValue({ response: { status: 500, data: { detail: "boom" } } });
  await act(async () => root.render(<MemoryRouter><Dashboard /></MemoryRouter>));
  await act(async () => {});
  expect(byId("error-block").textContent).toContain("boom");
  expect(byId("kpi-strip")).toBeNull();
});
