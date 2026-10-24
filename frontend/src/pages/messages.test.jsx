// The one-off message composer: a real e-mail is linked to a lead (its footer carries that lead's unsubscribe link), so the
// recipient is picked from or matched to the leads, and the server's refusal is shown as it is. API mocked, no network.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { api } from "@/lib/api";
import { toast } from "sonner";
import Messages from "@/pages/Messages";

global.IS_REACT_ACT_ENVIRONMENT = true;

const LEADS = [
  { id: "11111111-1111-4111-8111-111111111111", full_name: "Chez Marcel", company: "Marcel SARL", email: "contact@chez-marcel.example", phone: "+33 4 78 00 00 01", review_status: null },
  { id: "22222222-2222-4222-8222-222222222222", full_name: "Café des Quais", company: "Quais SAS", email: "bonjour@cafe-quais.example", phone: null, review_status: "approved" },
];

let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const type = async (id, value) => {
  await act(async () => {
    const el = byId(id);
    const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const click = async (id) => { await act(async () => { byId(id).click(); }); await act(async () => {}); };
const open = async (channel, leads = LEADS) => {
  api.get.mockImplementation((url) => {
    if (url === "/messages") return Promise.resolve({ data: [] });
    if (url === "/leads") return leads === null ? Promise.reject(new Error("boom")) : Promise.resolve({ data: leads });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  await act(async () => root.render(<MemoryRouter><Messages /></MemoryRouter>));
  await act(async () => {});
  await click(channel === "email" ? "new-email-button" : "new-whatsapp-button");
};

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  api.post.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("e-mail composer", () => {
  it("refuses an address that is not a lead, says why and sends nothing", async () => {
    await open("email");
    await type("compose-to", "stranger@elsewhere.example");
    await type("compose-body", "Hello");
    expect(byId("compose-no-lead").textContent).toContain("not one of your leads");
    expect(byId("compose-no-lead").querySelector("a").getAttribute("href")).toBe("/app/leads");
    expect(byId("send-message-button").disabled).toBe(true);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("links an address typed in another case to its lead and sends the lead_id with it", async () => {
    api.post.mockResolvedValue({ data: { result: { status: "sent" } } });
    await open("email");
    await type("compose-to", "  Contact@Chez-Marcel.example ");
    await type("compose-subject", "Hello");
    await type("compose-body", "Body");
    expect(byId("compose-lead").textContent).toContain("Linked to Chez Marcel");
    expect(byId("compose-no-lead")).toBeNull();
    expect(byId("send-message-button").disabled).toBe(false);
    await click("send-message-button");
    expect(api.post).toHaveBeenCalledWith("/messages/email", {
      to: "Contact@Chez-Marcel.example", subject: "Hello", body: "Body", lead_id: LEADS[0].id,
    });
    expect(toast.success).toHaveBeenCalledWith("Sent");
  });

  it("offers the leads while typing and fills the address from the one picked", async () => {
    api.post.mockResolvedValue({ data: { result: { status: "sent" } } });
    await open("email");
    await act(async () => { byId("compose-to").focus(); });
    expect(byId("compose-suggestions").textContent).toContain("Chez Marcel");
    await type("compose-to", "quais");
    expect(container.querySelectorAll('[data-testid^="compose-suggest-"]')).toHaveLength(1);
    await click("compose-suggest-0");
    expect(byId("compose-to").value).toBe("bonjour@cafe-quais.example");
    expect(byId("compose-lead").textContent).toContain("prospect: approved");
    await type("compose-body", "Body");
    await click("send-message-button");
    expect(api.post.mock.calls[0][1]).toMatchObject({ to: "bonjour@cafe-quais.example", lead_id: LEADS[1].id });
  });

  it("keeps the suggestions when the field is focused again before the list has closed", async () => {
    jest.useFakeTimers();
    try {
      await open("email");
      await act(async () => { byId("compose-to").focus(); });
      await act(async () => { byId("compose-body").focus(); }); // leaves the field: the list will close in a moment
      await act(async () => { byId("compose-to").focus(); jest.advanceTimersByTime(300); }); // back before it did
      expect(byId("compose-suggestions")).not.toBeNull();
      await act(async () => { byId("compose-body").focus(); jest.advanceTimersByTime(300); });
      expect(byId("compose-suggestions")).toBeNull(); // really left: it closes
    } finally {
      jest.useRealTimers();
    }
  });

  it("shows the server's refusal as it is", async () => {
    api.post.mockRejectedValue({ response: { status: 403, data: { detail: "Recipient cannot be contacted: review status is 'pending'" } } });
    await open("email");
    await type("compose-to", "contact@chez-marcel.example");
    await type("compose-body", "Body");
    await click("send-message-button");
    expect(toast.error).toHaveBeenCalledWith("Recipient cannot be contacted: review status is 'pending'");
  });

  it("says when the leads could not be loaded instead of letting an unlinked e-mail go", async () => {
    await open("email", null);
    await type("compose-to", "contact@chez-marcel.example");
    expect(byId("compose-leads-error").textContent).toContain("could not be loaded");
    expect(byId("send-message-button").disabled).toBe(true);
  });

  it("waits for the leads before judging an address", async () => {
    let release;
    api.get.mockImplementation((url) => (url === "/leads" ? new Promise((r) => { release = () => r({ data: LEADS }); }) : Promise.resolve({ data: [] })));
    await act(async () => root.render(<MemoryRouter><Messages /></MemoryRouter>));
    await click("new-email-button");
    await type("compose-to", "contact@chez-marcel.example");
    expect(byId("compose-no-lead")).toBeNull(); // not "unknown" yet: still loading
    expect(byId("send-message-button").disabled).toBe(true);
    await act(async () => { release(); });
    expect(byId("compose-lead")).not.toBeNull();
    expect(byId("send-message-button").disabled).toBe(false);
  });
});

describe("WhatsApp composer", () => {
  it("links a known number to its lead (the server checks its consent) and still lets the server judge an unknown one", async () => {
    api.post.mockResolvedValue({ data: { result: { status: "sent" } } });
    await open("whatsapp");
    await type("compose-to", "+33478000001");
    await type("compose-body", "Hi");
    expect(byId("compose-lead").textContent).toContain("Chez Marcel");
    await click("send-message-button");
    expect(api.post).toHaveBeenLastCalledWith("/messages/whatsapp", { to: "+33478000001", body: "Hi", lead_id: LEADS[0].id });

    await click("new-whatsapp-button"); // the composer closed after sending: open it again
    await type("compose-to", "+33600000099");
    await type("compose-body", "Hi");
    expect(byId("compose-no-lead")).toBeNull();
    expect(byId("send-message-button").disabled).toBe(false);
    await click("send-message-button");
    expect(api.post).toHaveBeenLastCalledWith("/messages/whatsapp", { to: "+33600000099", body: "Hi" });
  });
});
