/* global KeyboardEvent, MouseEvent */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { email: "me@example.test", role: "owner" }, org: { name: "Acme", plan: "pro" }, logout: jest.fn() }) }));
jest.mock("@/components/AIComposerModal", () => () => null);
jest.mock("@/components/Footer", () => () => null);

import Layout from "@/components/Layout";
import { SECTIONS } from "@/lib/sections";

global.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const render = async (path = "/app/dashboard") => { await act(async () => root.render(<MemoryRouter initialEntries={[path]}><Layout /></MemoryRouter>)); };
const click = async (el) => { await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };

beforeEach(() => { window.localStorage.clear(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("the sidebar has exactly six entries, flat, and the account is a footer, not a seventh entry", async () => {
  await render();
  const links = byId("sidebar").querySelectorAll("nav a");
  expect([...links].map((a) => a.textContent)).toEqual(["Vue d’ensemble", "Prospection", "Leads", "Batches", "Outreach", "Pilotage"]);
  expect(byId("sidebar").querySelectorAll("nav ul ul")).toHaveLength(0); // no tree
  expect(byId("sidebar").querySelectorAll("nav [aria-expanded]")).toHaveLength(0); // nothing to unfold
  expect(byId("account").textContent).toContain("Acme");
  expect(byId("account").textContent).toContain("me@example.test");
  expect(byId("account").closest("nav")).toBeNull();
});

test("the sidebar starts unfolded with its labels and the organisation", async () => {
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("sidebar").textContent).toContain("OUTREACHOS");
  expect(byId("org-name").textContent).toBe("Acme");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("true");
});

test("each entry leads to its section and the current one is marked", async () => {
  for (const section of SECTIONS) {
    await act(async () => root.unmount());
    root = createRoot(container);
    await render(section.to);
    expect(byId(`nav-${section.id}`).getAttribute("href")).toBe(section.to);
    expect(byId(`nav-${section.id}`).getAttribute("aria-current")).toBe("page");
    expect(container.querySelectorAll('[data-testid^="nav-"][aria-current="page"]')).toHaveLength(1);
  }
});

test("the tabs of the current section are the way to its other screens, and the current tab is marked", async () => {
  await render("/app/prospects/review");
  const tabs = [...byId("section-tabs").querySelectorAll("a")];
  expect(tabs.map((a) => a.textContent)).toEqual(["CRM", "Pipeline", "Prospects", "À vérifier", "À enrichir"]);
  expect(byId("tab-review").getAttribute("aria-current")).toBe("page");
  expect(byId("nav-leads").getAttribute("aria-current")).toBe("page");
  expect(byId("section-title").textContent).toBe("Leads");
});

test("Pipeline is a distinct tab and marks the Kanban route active, the CRM tab yields to it", async () => {
  await render("/app/leads?view=kanban");
  expect(byId("tab-pipeline").getAttribute("href")).toBe("/app/leads?view=kanban");
  expect(byId("tab-pipeline").getAttribute("aria-current")).toBe("page");
  expect(byId("tab-crm").getAttribute("aria-current")).toBeNull();
});

test("a prospect's sheet stays in Leads with its list marked", async () => {
  await render("/app/prospects/abc-123");
  expect(byId("nav-leads").getAttribute("aria-current")).toBe("page");
  expect(byId("tab-prospects").getAttribute("aria-current")).toBe("page");
});

test("the AI composer is one action of the section bar, not a button of the sidebar", async () => {
  await render();
  expect(byId("open-ai-composer")).not.toBeNull();
  expect(byId("sidebar").contains(byId("open-ai-composer"))).toBe(false);
  expect(byId("section-bar").contains(byId("open-ai-composer"))).toBe(true);
});

test("folding keeps every destination reachable by an accessible name and remembers the choice", async () => {
  await render();
  await click(byId("sidebar-toggle"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  expect(byId("sidebar").textContent).not.toContain("OUTREACHOS");
  expect(byId("nav-prospecting").getAttribute("aria-label")).toBe("Prospection");
  expect(byId("nav-control").getAttribute("title")).toBe("Pilotage");
  expect(byId("sidebar").querySelectorAll("nav a")).toHaveLength(6);
  expect(byId("logout-button").getAttribute("aria-label")).toBe("Déconnexion");
  expect(window.localStorage.getItem("pos.ui.sidebar.folded")).toBe("true");
  await act(async () => root.unmount());
  root = createRoot(container);
  await render(); // a later visit
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
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

test("mobile navigation opens an accessible drawer with the same six entries, traps the focus and gives it back", async () => {
  await render();
  expect(byId("mobile-drawer")).toBeNull();
  await click(byId("mobile-nav-toggle"));
  expect(byId("mobile-drawer")).not.toBeNull();
  expect(byId("mobile-drawer").querySelectorAll("nav a")).toHaveLength(6);
  expect(byId("mobile-nav-batches")).not.toBeNull();
  expect(byId("mobile-drawer").parentElement.getAttribute("aria-modal")).toBe("true");
  expect(byId("mobile-drawer").getAttribute("aria-label")).toContain("Navigation");
  expect(document.activeElement.getAttribute("aria-label")).toBe("Fermer la navigation");
  // Tab from the last control wraps to the first, Shift+Tab from the first wraps to the last
  const focusable = byId("mobile-drawer").querySelectorAll("a[href], button:not([disabled])");
  focusable[focusable.length - 1].focus();
  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" })));
  expect(document.activeElement).toBe(focusable[0]);
  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
  expect(byId("mobile-drawer")).toBeNull();
  expect(document.activeElement).toBe(byId("mobile-nav-toggle"));
});

test("choosing an entry in the drawer closes it", async () => {
  await render();
  await click(byId("mobile-nav-toggle"));
  await click(byId("mobile-nav-outreach"));
  expect(byId("mobile-drawer")).toBeNull();
});
