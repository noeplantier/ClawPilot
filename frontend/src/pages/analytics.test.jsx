import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn() } }));

import { api } from "@/lib/api";
import Analytics from "@/pages/Analytics";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const show = async () => { await act(async () => root.render(<Analytics />)); await act(async () => {}); };

beforeEach(() => { jest.clearAllMocks(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("an account with no activity gets explicit empty states, never invented numbers", async () => {
  api.get.mockResolvedValue({ data: { totals: {}, timeseries: [{ date: "2026-10-01", replied: 0, opened: 0 }], pipeline: {}, top_countries: [] } });
  await show();
  for (const id of ["funnel-empty", "velocity-empty", "pipeline-empty", "countries-empty"]) expect(byId(id)).not.toBeNull();
  expect(container.querySelector("svg[role=img]")).toBeNull(); // no chart is drawn from nothing
});

test("with data, the charts print the exact figures from the API", async () => {
  api.get.mockResolvedValue({
    data: {
      totals: { sent: 12, opened: 5, replied: 2, converted: 1 },
      timeseries: [{ date: "2026-10-01", replied: 1, opened: 3 }, { date: "2026-10-02", replied: 1, opened: 2 }],
      pipeline: { new: 4, won: 1 },
      top_countries: [{ country: "FR", leads: 7 }],
    },
  });
  await show();
  const text = container.textContent;
  expect(text).toContain("12");
  expect(text).toContain("Converted");
  expect(container.querySelector('svg[aria-label="Leads per country"] title').textContent).toBe("FR: 7");
  expect(byId("funnel-empty")).toBeNull();
});

test("a failed request shows a retryable error instead of an endless loading message", async () => {
  api.get.mockRejectedValueOnce(new Error("boom"));
  await show();
  expect(container.textContent).toContain("Could not load the analytics");
  api.get.mockResolvedValueOnce({ data: { totals: { sent: 1 }, timeseries: [], pipeline: {}, top_countries: [] } });
  await act(async () => { container.querySelector("button").click(); });
  await act(async () => {});
  expect(container.textContent).toContain("Conversion Funnel");
});
