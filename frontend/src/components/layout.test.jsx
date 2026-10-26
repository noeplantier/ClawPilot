/* global KeyboardEvent, MouseEvent */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { email: "me@example.test", role: "owner" }, org: { name: "Acme", plan: "pro" }, logout: jest.fn() }) }));
jest.mock("@/components/AIComposerModal", () => () => null);
jest.mock("@/components/Footer", () => () => null);

import Layout from "@/components/Layout";

global.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const render = async (path = "/app/dashboard") => { await act(async () => root.render(<MemoryRouter initialEntries={[path]}><Layout /></MemoryRouter>)); };
const click = async (el) => { await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };

beforeEach(() => { window.localStorage.clear(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("the sidebar starts unfolded with its labels and the organisation", async () => {
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("sidebar").textContent).toContain("OUTREACHOS");
  expect(byId("sidebar").textContent).toContain("PLANTIERS");
  expect(byId("org-name").textContent).toBe("Acme");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("true");
});

test("folding keeps every destination reachable through accessible group controls and remembers the choice", async () => {
  await render();
  await click(byId("sidebar-toggle"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  expect(byId("sidebar").textContent).not.toContain("OUTREACHOS");
  expect(byId("nav-group-prospecting").getAttribute("aria-label")).toBe("Prospection");
  expect(byId("nav-group-control").getAttribute("title")).toBe("Pilotage");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("false");
  expect(window.localStorage.getItem("pos.ui.sidebar.folded")).toBe("true");
  await act(async () => root.unmount());
  root = createRoot(container);
  await render(); // a later visit
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  await click(byId("nav-group-prospecting"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("nav-map-search")).not.toBeNull();
});

test("the [ key folds and unfolds, except while typing in a field", async () => {
  await render();
  const press = async (target) => act(async () => { target.dispatchEvent(new KeyboardEvent("keydown", { key: "[", bubbles: true })); });
  await press(document.body);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  const input = document.createElement("input");
  document.body.appendChild(input);
  await press(input);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true"); // typing: ignored
  input.remove();
  await press(document.body);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
});

test("mobile navigation opens an accessible drawer with grouped destinations", async () => {
  await render();
  expect(byId("mobile-nav")).toBeNull();
  await click(byId("mobile-nav-toggle"));
  expect(byId("mobile-drawer")).not.toBeNull();
  expect(byId("mobile-drawer").querySelectorAll("a")).toHaveLength(1);
  await click(byId("mobile-nav-group-prospecting"));
  expect(byId("mobile-drawer").querySelectorAll("a")).toHaveLength(5);
  await click(byId("mobile-nav-group-crm"));
  expect(byId("mobile-nav-leads-crm")).not.toBeNull();
  expect(byId("mobile-nav-pipeline")).not.toBeNull();
  expect(byId("mobile-drawer").parentElement.getAttribute("aria-modal")).toBe("true");
  expect(byId("mobile-drawer").getAttribute("aria-label")).toContain("Navigation");
  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
  expect(byId("mobile-drawer")).toBeNull();
  expect(document.activeElement).toBe(byId("mobile-nav-toggle"));
});

test("Pipeline is a distinct CRM destination and marks the Kanban route active", async () => {
  await render("/app/leads?view=kanban");
  expect(byId("nav-pipeline").getAttribute("href")).toBe("/app/leads?view=kanban");
  expect(byId("nav-pipeline").getAttribute("aria-current")).toBe("page");
  expect(byId("nav-leads-crm").getAttribute("aria-current")).toBeNull();
});
