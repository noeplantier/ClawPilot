import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { api } from "@/lib/api";
import SignalList from "@/components/outreach/SignalList";

global.IS_REACT_ACT_ENVIRONMENT = true;

const SIGNALS = [
  { key: "no_website", label: "No own website listed", state: "detected", evidence: "No website listed in annuaire", observed_at: "2026-06-01T10:00:00Z" },
  { key: "stale_listing", label: "Listing not updated recently", state: "unknown", evidence: "The source gives no last-updated date", observed_at: "2026-06-01T10:00:00Z" },
  { key: "booking_page_missing", label: "No online booking", state: "unknown", evidence: "No booking link", observed_at: "2026-06-01T10:00:00Z", dismissed: true, dismissed_reason: "they do take bookings", observed_state: "detected" },
];

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const render = async (props) => { await act(async () => root.render(<SignalList signals={SIGNALS} prospectId="p1" onChanged={jest.fn()} {...props} />)); };
const type = async (id, value) => {
  const el = byId(id);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setter.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
};

beforeEach(() => { jest.clearAllMocks(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("a reviewer can dismiss a finding only with a reason; unknown signals offer nothing to dismiss", async () => {
  api.post.mockResolvedValue({ data: {} });
  const onChanged = jest.fn();
  await render({ canReview: true, onChanged });
  expect(byId("dismiss-stale_listing")).toBeNull(); // nothing to dismiss on an unknown signal
  await act(async () => byId("dismiss-no_website").click());
  expect(byId("dismiss-confirm-no_website").disabled).toBe(true);
  await type("dismiss-reason-no_website", "abc");
  expect(byId("dismiss-confirm-no_website").disabled).toBe(true); // too short
  await type("dismiss-reason-no_website", "the shop has a site");
  await act(async () => byId("dismiss-confirm-no_website").click());
  expect(api.post).toHaveBeenCalledWith("/prospects/p1/signals/no_website/dismiss", { reason: "the shop has a site" });
  expect(onChanged).toHaveBeenCalled();
});

test("a dismissed signal says so, shows what was observed and can be restored", async () => {
  api.post.mockResolvedValue({ data: {} });
  await render({ canReview: true });
  expect(byId("dismissed-booking_page_missing").textContent).toContain("they do take bookings");
  expect(byId("dismissed-booking_page_missing").textContent).toContain("Observed: detected");
  await act(async () => byId("restore-booking_page_missing").click());
  expect(api.post).toHaveBeenCalledWith("/prospects/p1/signals/booking_page_missing/restore");
});

test("without review rights nothing can be changed", async () => {
  await render({ canReview: false });
  expect(byId("dismiss-no_website")).toBeNull();
  expect(byId("restore-booking_page_missing")).toBeNull();
});
