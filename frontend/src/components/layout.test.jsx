/* global KeyboardEvent, MouseEvent */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { email: "me@example.test", role: "owner" },
    org: { name: "Acme", plan: "pro" },
    logout: jest.fn(),
  }),
}));
jest.mock("@/components/AIComposerModal", () => () => null);
jest.mock("@/components/Footer", () => () => null);

import Layout from "@/components/Layout";
import { SECTIONS } from "@/lib/sections";

global.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const render = async (path = "/app/dashboard") => {
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}><Layout /></MemoryRouter>));
};
const click = async (el) => {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
};

beforeEach(() => {
  window.localStorage.clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("the sidebar displays exactly the six Plantiers rubriques", async () => {
  await render();
  const links = [...byId("sidebar").querySelectorAll('a[data-testid^="nav-"]')];
  expect(links.map((a) => a.textContent)).toEqual(SECTIONS.map((s) => s.label));
  expect(links).toHaveLength(6);
  expect(byId("account").textContent).toContain("Acme");
  expect(byId("account").textContent).toContain("me@example.test");
  expect(byId("account").closest("nav")).toBeNull();
});

test("the sidebar starts unfolded with its branding and the organisation", async () => {
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("sidebar").textContent).toContain("PLANTIERS");
  expect(byId("sidebar").textContent).toContain("OUTREACH OS");
  expect(byId("org-name").textContent).toBe("Acme");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("true");
});

test("each rubrique has its link, tooltip and an active state", async () => {
  for (const section of SECTIONS) {
    await act(async () => root.unmount());
    root = createRoot(container);
    await render(section.to);
    const link = byId(section.testId);
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe(section.to);
    expect(link.getAttribute("aria-current")).toBe("page");
    expect(link.getAttribute("title")).toBe(section.label);
  }
});

test("a sub-section keeps its parent rubrique active", async () => {
  await render("/app/prospects/review");
  expect(byId("nav-leads").getAttribute("aria-current")).toBe("page");
  expect(byId("nav-prospecting").getAttribute("aria-current")).toBeNull();
});

test("only the decision tabs of the current section are displayed for Leads", async () => {
  await render("/app/prospects/review");
  const tabs = [...byId("section-tabs").querySelectorAll("a")];
  expect(tabs.map((a) => a.textContent)).toEqual(["CRM", "À vérifier", "À enrichir"]);
  expect(byId("tab-review").getAttribute("aria-current")).toBe("page");
});

test("advanced screens stay reachable in a details panel instead of the primary tabs", async () => {
  await render("/app/leads");
  expect(byId("tab-pipeline")).toBeNull();
  expect(byId("details-toggle").getAttribute("aria-expanded")).toBe("false");
  await click(byId("details-toggle"));
  expect(byId("details-panel")).not.toBeNull();
  expect([...byId("details-panel").querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Pipeline", "Prospects"]);
  await click(byId("details-panel").querySelector('a[href="/app/prospects"]'));
  expect(byId("details-panel")).toBeNull();
});

test("offer approval sits beside the answers it drives", async () => {
  await render("/app/drafts");
  await click(byId("details-toggle"));
  expect(byId("detail-offer").textContent).toBe("Offre & modèle");
  expect(byId("detail-offer").getAttribute("href")).toBe("/app/settings/offer");
});

test("upper navigation elements are removed for Offer, Integrations, Automations, System Health", async () => {
  for (const p of ["/app/settings/offer", "/app/settings", "/app/agents", "/app/system"]) {
    await act(async () => root.unmount());
    root = createRoot(container);
    await render(p);
    expect(byId("section-tabs")).toBeNull();
    expect(byId("details-toggle")).toBeNull();
  }
});

test("the AI composer is one action of the section bar, not inside sidebar navigation", async () => {
  await render();
  expect(byId("open-ai-composer")).not.toBeNull();
  expect(byId("sidebar").contains(byId("open-ai-composer"))).toBe(false);
  expect(byId("section-bar").contains(byId("open-ai-composer"))).toBe(true);
});

test("folding keeps destinations reachable with aria-label and remembers choice", async () => {
  await render();
  await click(byId("sidebar-toggle"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  expect(byId("nav-overview").getAttribute("aria-label")).toBe("Vue d’ensemble");
  expect(byId("nav-prospecting").getAttribute("aria-label")).toBe("Prospection");
  expect(window.localStorage.getItem("pos.ui.sidebar.folded")).toBe("true");
  await act(async () => root.unmount());
  root = createRoot(container);
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
});

test("the [ key folds and unfolds, except while typing in a field", async () => {
  await render();
  const press = async (target) =>
    act(async () => {
      target.dispatchEvent(new KeyboardEvent("keydown", { key: "[", bubbles: true }));
    });
  await press(document.body);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  const input = document.createElement("input");
  document.body.appendChild(input);
  await press(input);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  input.remove();
  await press(document.body);
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
});

test("mobile navigation opens an accessible drawer, traps focus and closes on Escape", async () => {
  await render();
  expect(byId("mobile-drawer")).toBeNull();
  await click(byId("mobile-nav-toggle"));
  expect(byId("mobile-drawer")).not.toBeNull();
  expect(byId("mobile-nav-overview")).not.toBeNull();
  expect(byId("mobile-drawer").parentElement.getAttribute("aria-modal")).toBe("true");
  expect(byId("mobile-drawer").getAttribute("aria-label")).toContain("Navigation");
  expect(document.activeElement.getAttribute("aria-label")).toBe("Fermer la navigation");

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
  await click(byId("mobile-nav-overview"));
  expect(byId("mobile-drawer")).toBeNull();
});
