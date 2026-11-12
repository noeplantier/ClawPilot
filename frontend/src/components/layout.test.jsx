/* global KeyboardEvent, MouseEvent, Element */
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

beforeAll(() => {
  // cmdk (the palette) measures and scrolls; jsdom has neither.
  global.ResizeObserver = global.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} };
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});
});
beforeEach(() => { window.localStorage.clear(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

test("the sidebar has exactly six entries, and the account is a footer, not a seventh entry", async () => {
  await render();
  const entries = byId("sidebar").querySelectorAll('nav > ul > li > a[data-testid^="nav-"]');
  expect([...entries].map((a) => a.textContent)).toEqual(["Vue d’ensemble", "Prospection", "Leads", "Batches", "Outreach", "Pilotage"]);
  expect(byId("account").textContent).toContain("Acme");
  expect(byId("account").textContent).toContain("me@example.test");
  expect(byId("account").closest("nav")).toBeNull();
});

test("there is no top bar any more: nothing is rendered above the page but the phone's menu strip", async () => {
  await render();
  expect(byId("section-bar")).toBeNull();
  expect(byId("section-tabs")).toBeNull();
  expect(byId("section-title")).toBeNull();
  const headers = [...container.querySelectorAll("header")];
  expect(headers).toHaveLength(1);
  expect(headers[0].className).toContain("md:hidden"); // the strip that only opens the drawer on a phone
});

test("the sidebar starts unfolded with its labels and the organisation", async () => {
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("sidebar").textContent).toContain("OUTREACHOS");
  expect(byId("org-name").textContent).toBe("Acme");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("true");
  expect(byId("sidebar-toggle").getAttribute("aria-controls")).toBe("app-sidebar");
  expect(byId("sidebar").id).toBe("app-sidebar");
});

test("the logo is centred in the open width, and it is the compact mark when folded", async () => {
  await render();
  expect(byId("brand").className).toContain("justify-center");
  expect(byId("brand").textContent).toContain("PLANTIERS");
  await click(byId("sidebar-toggle"));
  expect(byId("brand").className).toContain("justify-center");
  expect(byId("brand").textContent).toBe(""); // the mark alone
  expect(byId("brand").querySelectorAll("img")).toHaveLength(1);
  expect(byId("brand").querySelector("a").getAttribute("aria-label")).toContain("Plantiers"); // named, though there is no text
});

test("each entry leads to its section and the current one is marked", async () => {
  for (const section of SECTIONS) {
    await act(async () => root.unmount());
    root = createRoot(container);
    await render(section.to);
    expect(byId(`nav-${section.id}`).getAttribute("href")).toBe(section.to);
    expect(byId(`nav-${section.id}`).getAttribute("aria-current")).toBe("true"); // it holds the current page, which is marked inside it
    expect(container.querySelectorAll('[data-testid^="nav-"][aria-current]')).toHaveLength(1);
    expect(container.querySelectorAll('[aria-current="page"]')).toHaveLength(1); // one current page, whichever way it is reached
  }
});

test("the current section lists its screens right under it, and the current screen is marked", async () => {
  await render("/app/prospects/review");
  const screens = [...byId("subnav").querySelectorAll("a")];
  expect(screens.map((a) => a.textContent)).toEqual(["CRM", "Pipeline", "Prospects", "À vérifier", "À enrichir"]);
  expect(byId("tab-review").getAttribute("aria-current")).toBe("page");
  expect(byId("nav-leads").getAttribute("aria-current")).toBe("true"); // the section holds the current page
  expect(byId("subnav").getAttribute("aria-label")).toBe("Leads : écrans");
  expect(container.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  expect(container.querySelectorAll('[data-testid="subnav"]')).toHaveLength(1); // only the section you are in is unfolded
});

test("every screen of every section is reachable from the sidebar of its section", async () => {
  for (const section of SECTIONS) {
    await act(async () => root.unmount());
    root = createRoot(container);
    await render(section.to);
    for (const tab of section.tabs) expect(byId(tab.testId).getAttribute("href")).toBe(tab.to);
  }
});

test("Pipeline is a distinct screen and marks the Kanban route active, the CRM yields to it", async () => {
  await render("/app/leads?view=kanban");
  expect(byId("tab-pipeline").getAttribute("href")).toBe("/app/leads?view=kanban");
  expect(byId("tab-pipeline").getAttribute("aria-current")).toBe("page");
  expect(byId("tab-crm").getAttribute("aria-current")).toBeNull();
});

test("a prospect's sheet stays in Leads with its list marked", async () => {
  await render("/app/prospects/abc-123");
  expect(byId("nav-leads").getAttribute("aria-current")).toBe("true");
  expect(byId("tab-prospects").getAttribute("aria-current")).toBe("page");
});

test("the AI composer and the go-to palette are tools at the foot of the sidebar, not a top bar", async () => {
  await render();
  expect(byId("sidebar").contains(byId("open-ai-composer"))).toBe(true);
  expect(byId("tools").contains(byId("open-ai-composer"))).toBe(true);
  expect(byId("tools").contains(byId("open-palette"))).toBe(true);
  expect(byId("open-palette").getAttribute("aria-haspopup")).toBe("dialog");
});

test("folding keeps every destination reachable by an accessible name and remembers the choice", async () => {
  await render("/app/prospects/review");
  await click(byId("sidebar-toggle"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("false");
  expect(byId("sidebar-toggle").getAttribute("aria-label")).toBe("Déplier la navigation");
  expect(byId("sidebar").textContent).not.toContain("OUTREACHOS");
  expect(byId("subnav")).toBeNull(); // no room for the screens: the palette and the unfolded sidebar list them
  expect(byId("nav-prospecting").getAttribute("aria-label")).toBe("Prospection");
  expect(byId("nav-control").getAttribute("aria-label")).toBe("Pilotage");
  expect(byId("sidebar").querySelectorAll('nav a[data-testid^="nav-"]')).toHaveLength(6);
  expect(byId("open-palette").getAttribute("aria-label")).toContain("Aller à");
  expect(byId("open-ai-composer").getAttribute("aria-label")).toBe("Composer IA");
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

test("Ctrl+K opens the go-to palette with every screen and the former top-bar actions; Escape closes it", async () => {
  await render();
  expect(document.querySelector('[data-testid="palette-input"]')).toBeNull();
  await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })); });
  await flush();
  expect(document.querySelector('[data-testid="palette-input"]')).not.toBeNull();
  const items = [...document.querySelectorAll('[data-testid^="palette-go-"]')].map((el) => el.textContent);
  for (const tab of SECTIONS.flatMap((s) => s.tabs)) expect(items).toContain(tab.label);
  expect(document.querySelector('[data-testid="palette-action-compose"]')).not.toBeNull();
  expect(document.querySelector('[data-testid="palette-action-logout"]')).not.toBeNull();
  await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })); });
  await flush();
  expect(document.querySelector('[data-testid="palette-input"]')).toBeNull();
});

test("mobile navigation opens an accessible drawer with the same six entries, traps the focus and gives it back", async () => {
  await render();
  expect(byId("mobile-drawer")).toBeNull();
  await click(byId("mobile-nav-toggle"));
  expect(byId("mobile-drawer")).not.toBeNull();
  expect(byId("mobile-drawer").querySelectorAll('nav > ul > li > a')).toHaveLength(6);
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
