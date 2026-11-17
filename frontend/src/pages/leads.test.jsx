import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import Leads from "@/pages/Leads";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const click = async (id) => {
  await act(async () => byId(id).click());
  await act(async () => {});
};
const type = async (id, value) => {
  await act(async () => {
    const input = byId(id);
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
};

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockResolvedValue({ data: [] });
  api.post.mockReset().mockResolvedValue({ data: {} });
  toast.success.mockReset();
  toast.error.mockReset();
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.useRealTimers();
});

it("creates a name-only lead by sending blank optional fields as null", async () => {
  await act(async () => root.render(<MemoryRouter><Leads /></MemoryRouter>));
  await act(async () => {});
  await click("add-lead-button");
  await type("lead-full_name", "Only a name");
  await click("save-lead-button");

  expect(api.post).toHaveBeenCalledWith("/leads", {
    full_name: "Only a name", email: null, phone: null, company: null, title: null, country: null,
    language: "en",
  });
  expect(toast.success).toHaveBeenCalledWith("Lead added");
  expect(toast.error).not.toHaveBeenCalled();
  expect(byId("close-create-lead")).toBeNull();
});

it("shows a newly persisted qualification score through the live refresh", async () => {
  jest.useFakeTimers();
  const lead = {
    id: "lead-1", full_name: "Scored company", company: "Scored company", country: "FR", stage: "new", score: 0,
    heat: { value: 20, tier: "cold", known: ["website"], missing: [], scored: false, top: false, has_contact: true },
    enrichment_status: "completed", fit_score: null, website_quality: null, digital_maturity: null, priority: null,
  };
  let listCalls = 0;
  api.get.mockReset().mockImplementation((url) => {
    if (url === "/leads/count") return Promise.resolve({ data: { total: 1 } });
    listCalls += 1;
    return Promise.resolve({ data: [listCalls === 1 ? lead : { ...lead, fit_score: 82, website_quality: 75, digital_maturity: 70, priority: "high" }] });
  });

  await act(async () => root.render(<MemoryRouter><Leads /></MemoryRouter>));
  expect(byId("qualification-lead-1").textContent).toContain("Scoring requis");

  await act(async () => { jest.advanceTimersByTime(15000); await Promise.resolve(); });
  expect(byId("qualification-lead-1").textContent).toContain("Fit 82");
  expect(byId("qualification-lead-1").textContent).toContain("Website 75 · Digital 70");
  expect(listCalls).toBe(2);
});

it("shows unavailable qualification fields as unknown rather than empty or negative", async () => {
  const lead = {
    id: "lead-unknown", full_name: "Unknown data", company: "Unknown data", country: "FR", stage: "new", score: 0,
    heat: { value: 20, tier: "cold", known: ["website"], missing: [], scored: true, top: false, has_contact: true },
    enrichment_status: "completed", fit_score: 20, website_quality: null, digital_maturity: null, priority: null,
  };
  api.get.mockResolvedValue({ data: [lead] });
  await act(async () => root.render(<MemoryRouter><Leads /></MemoryRouter>));
  const qualification = byId("qualification-lead-unknown");
  expect(qualification.textContent).toContain("Unknown");
  expect(qualification.textContent).toContain("Website Unknown · Digital Unknown");
  expect(qualification.querySelector(".chip").className).toContain("chip-ink");
});

const LEAD = (id, over = {}) => ({
  id, full_name: `Lead ${id}`, company: "Co", country: "FR", stage: "new", score: 0, review_status: "approved",
  heat: { value: 50, tier: "warm", known: ["email"], missing: [], scored: true, top: false, has_contact: true },
  enrichment_status: "completed", fit_score: null, website_quality: null, digital_maturity: null, priority: null, email: `${id}@x.example`, ...over,
});

it("says when the list is cut, from the server's real total", async () => {
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/leads/count" ? { total: 640 } : [LEAD("a"), LEAD("b")] }));
  await act(async () => root.render(<MemoryRouter><Leads /></MemoryRouter>));
  await act(async () => {});
  expect(byId("leads-cut").textContent).toContain("2 leads affichés sur 640");
  expect(byId("leads-cut").textContent).toContain("filtrez « Approuvés »");
});

it("filters the approved ones on the server, and says nothing when nothing is cut", async () => {
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/leads/count" ? { total: 1 } : [LEAD("a")] }));
  await act(async () => root.render(<MemoryRouter initialEntries={["/app/leads?review=approved"]}><Leads /></MemoryRouter>));
  await act(async () => {});
  expect(api.get).toHaveBeenCalledWith("/leads", { params: { search: "", sort: "heat", review_status: "approved" } });
  expect(api.get).toHaveBeenCalledWith("/leads/count", { params: { search: "", review_status: "approved" } });
  expect(byId("review-filter-approved").getAttribute("aria-pressed")).toBe("true");
  expect(byId("leads-cut")).toBeNull();
});

it("opens the lead named in the address, wherever it ranks", async () => {
  api.get.mockImplementation((url) => Promise.resolve({ data: url === "/leads/count" ? { total: 900 } : url === "/leads/far" ? LEAD("far") : [LEAD("a")] }));
  await act(async () => root.render(<MemoryRouter initialEntries={["/app/leads?lead=far"]}><Leads /></MemoryRouter>));
  await act(async () => {});
  expect(api.get).toHaveBeenCalledWith("/leads/far");
});

it("has one map only: the CRM's map view opens Prospection › Carte", async () => {
  const { Routes, Route } = jest.requireActual("react-router-dom");
  await act(async () => root.render(
    <MemoryRouter initialEntries={["/app/leads?view=map"]}>
      <Routes>
        <Route path="/app/leads" element={<Leads />} />
        <Route path="/app/map" element={<p data-testid="the-map">map</p>} />
      </Routes>
    </MemoryRouter>,
  ));
  await act(async () => {});
  expect(byId("the-map")).not.toBeNull();
});
