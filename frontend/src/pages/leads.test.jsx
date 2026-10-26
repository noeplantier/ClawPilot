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
