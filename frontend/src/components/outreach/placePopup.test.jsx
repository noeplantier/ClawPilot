// The popup of a map pin: what the map published, the attestation gate, and the one-click addition. API mocked, no network.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));

import { api } from "@/lib/api";
import PlacePopup from "@/components/outreach/PlacePopup";
import AddedCard from "@/components/outreach/AddedCard";

global.IS_REACT_ACT_ENVIRONMENT = true;

const PLACE = {
  external_id: "node/7", name: "Boulangerie Sept", lat: 45.76, lon: 4.835, city: "Lyon", phone: null, email: null,
  website: "https://sept.example", source_url: "https://www.openstreetmap.org/node/7",
};
const ADDED = { lead_id: "p1", name: "Boulangerie Sept", created: true, review_status: "approved", in_crm: true, email: "contact@sept.example", phone: null, website: "https://sept.example", email_found_on_site: true, website_checked: true };

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const mount = async (props = {}, onAdded = jest.fn()) => {
  await act(async () => root.render(<MemoryRouter><PlacePopup place={PLACE} canAdd offReason={null} onAdded={onAdded} {...props} /></MemoryRouter>));
  return onAdded;
};
const click = async (id) => { await act(async () => { byId(id).click(); }); await act(async () => {}); };

beforeEach(() => {
  window.localStorage.clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.post.mockReset();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("PlacePopup", () => {
  it("shows only what was published and says 'not published' for the rest", async () => {
    await mount();
    const text = container.textContent;
    expect(text).toContain("Boulangerie Sept");
    expect(text).toContain("Lyon");
    expect(text).toContain("https://sept.example");
    expect(text).toContain("not published"); // the phone and the e-mail
    expect(text).toContain("source on OpenStreetMap");
  });

  it("cannot add until the person attests, then sends the place, the attestation and the website choice", async () => {
    const onAdded = await mount();
    expect(byId("place-add").disabled).toBe(true);
    expect(byId("place-add-review").disabled).toBe(true);
    await click("place-attest");
    expect(byId("place-add").disabled).toBe(false);
    api.post.mockResolvedValue({ data: ADDED });
    await click("place-add");
    expect(api.post).toHaveBeenCalledWith("/map/places/add", expect.objectContaining({ attestation: true, approve: true, check_website: true }));
    expect(api.post.mock.calls[0][1].place).toMatchObject({ external_id: "node/7", name: "Boulangerie Sept", website: "https://sept.example" });
    expect(api.post.mock.calls[0][1].place.email).toBeUndefined();
    expect(byId("place-done").textContent).toContain("Added to your CRM");
    // the full account (what was found, that nothing was sent) is the map's job: it keeps it on screen after the pin is rebuilt
    expect(onAdded).toHaveBeenCalledWith(ADDED, PLACE, { siteAsked: true });
  });

  it("'for review' leaves the decision to the review queue", async () => {
    await mount();
    await click("place-attest");
    api.post.mockResolvedValue({ data: { ...ADDED, review_status: "pending", in_crm: false } });
    await click("place-add-review");
    expect(api.post.mock.calls[0][1].approve).toBe(false);
    expect(byId("place-done").textContent).toContain("waits for review");
  });

  it("reading the website is the person's choice and is not offered for a place without one", async () => {
    await mount();
    await click("place-read-site"); // untick
    await click("place-attest");
    api.post.mockResolvedValue({ data: ADDED });
    await click("place-add");
    expect(api.post.mock.calls[0][1].check_website).toBe(false);
    await act(async () => root.unmount());
    root = createRoot(container);
    await mount({ place: { ...PLACE, website: null } });
    expect(byId("place-read-site")).toBeNull();
  });

  it("remembers the attestation on this browser, and a server refusal is shown, not swallowed", async () => {
    await mount();
    await click("place-attest");
    await act(async () => root.unmount());
    root = createRoot(container);
    await mount();
    expect(byId("place-attest").checked).toBe(true);
    api.post.mockRejectedValue({ response: { status: 403, data: { detail: { code: "feature_disabled", message: "Adding places needs FEATURE_PROSPECT_IMPORT (off by default)", retry_at: null } } } });
    await click("place-add");
    expect(byId("place-error").textContent).toContain("FEATURE_PROSPECT_IMPORT");
    expect(byId("place-done")).toBeNull();
  });

  it("explains why adding is off instead of showing a dead button", async () => {
    await mount({ canAdd: false, offReason: "Adding places is off: set FEATURE_PROSPECT_IMPORT=true on the server." });
    expect(byId("place-add")).toBeNull();
    expect(byId("place-add-off").textContent).toContain("FEATURE_PROSPECT_IMPORT");
  });
});

describe("AddedCard", () => {
  it("keeps the account of what happened on screen, with the way to the CRM and to the prospect", async () => {
    const onClose = jest.fn();
    await act(async () => root.render(<MemoryRouter><AddedCard out={ADDED} siteAsked onClose={onClose} /></MemoryRouter>));
    const text = byId("place-added").textContent;
    expect(text).toContain("In your CRM");
    expect(text).toContain("found on its own website");
    expect(text).toContain("Nothing was sent");
    expect(byId("place-open-crm").getAttribute("href")).toBe("/app/leads");
    expect(byId("place-open-prospect").getAttribute("href")).toBe("/app/prospects/p1");
    await click("place-added-close");
    expect(onClose).toHaveBeenCalled();
  });
});
