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
const render = async () => { await act(async () => root.render(<MemoryRouter initialEntries={["/app/dashboard"]}><Layout /></MemoryRouter>)); };
const click = async (el) => { await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };

beforeEach(() => { window.localStorage.clear(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("the sidebar starts unfolded with its labels and the organisation", async () => {
  await render();
  expect(byId("sidebar").getAttribute("data-folded")).toBe("false");
  expect(byId("sidebar").textContent).toContain("OUTREACHOS");
  expect(byId("sidebar").textContent).toContain("/// command.center");
  expect(byId("org-name").textContent).toBe("Acme");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("true");
});

test("folding keeps every destination reachable by icon with an accessible name, and remembers the choice", async () => {
  await render();
  await click(byId("sidebar-toggle"));
  expect(byId("sidebar").getAttribute("data-folded")).toBe("true");
  expect(byId("sidebar").textContent).not.toContain("OUTREACHOS");
  expect(byId("nav-map-search").getAttribute("aria-label")).toBe("Map search");
  expect(byId("nav-settings").getAttribute("title")).toBe("Settings");
  expect(byId("sidebar-toggle").getAttribute("aria-expanded")).toBe("false");
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

test("a mobile navigation lists the same destinations", async () => {
  await render();
  expect(byId("mobile-nav").querySelectorAll("a")).toHaveLength(13);
});
