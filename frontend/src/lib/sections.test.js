/* global require, __dirname */
import { NAV_GROUPS, SECTIONS, activeNavItem, activeTab, pathOf, sectionOf } from "@/lib/sections";

const fs = require("fs");
const path = require("path");

// Every path declared under <Route path="/app"> in App.js, with the dynamic ones given a sample value.
const appRoutes = () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "App.js"), "utf8");
  const inside = source.slice(source.indexOf('path="/app"'), source.indexOf('path="*"'));
  return [...inside.matchAll(/<Route\s+(?:index\s+)?path="([^"]+)"/g)].map((m) => `/app/${m[1].replace(":id", "p1")}`);
};

test("the sidebar navigation is structured into MAIN, INTELLIGENCE and CONFIGURATION groups", () => {
  expect(NAV_GROUPS.map((g) => g.id)).toEqual(["main", "intelligence", "configuration"]);
  const allNavItems = NAV_GROUPS.flatMap((g) => g.items);
  expect(allNavItems.length).toBeGreaterThanOrEqual(11);
  expect(allNavItems.map((item) => item.label)).toEqual(
    expect.arrayContaining([
      "Dashboard",
      "Live Prospect Map",
      "Leads",
      "Campaigns",
      "Analytics",
      "AI Draft Generator",
      "Automations",
      "Lead Qualification",
      "Offer & Services",
      "Integrations",
      "Settings",
      "System Health",
    ])
  );
});

test("every screen of the application belongs to a section or nav group: nothing useful is unreachable", () => {
  const routes = appRoutes();
  expect(routes.length).toBeGreaterThan(14);
  const orphans = routes.filter((r) => !sectionOf(r) && !activeNavItem(r));
  expect(orphans).toEqual([]);
});

test("every nav item and tab leads to a screen that exists", () => {
  const known = new Set(appRoutes().map(pathOf));
  const navPaths = NAV_GROUPS.flatMap((g) => g.items).map((item) => pathOf(item.to));
  const missingNav = navPaths.filter((p) => !known.has(p));
  expect(missingNav).toEqual([]);

  const tabPaths = SECTIONS.flatMap((s) => s.tabs).map((t) => pathOf(t.to));
  const missingTabs = tabPaths.filter((p) => !known.has(p));
  expect(missingTabs).toEqual([]);
});

test("a path lands in the section that holds it, the nested screen under its own tab", () => {
  const id = (p) => (sectionOf(p) || {}).id;
  expect(id("/app/dashboard")).toBe("overview");
  expect(id("/app/analytics")).toBe("overview");
  expect(id("/app/map")).toBe("prospecting");
  expect(id("/app/prospects/import")).toBe("prospecting");
  expect(id("/app/prospects")).toBe("leads");
  expect(id("/app/prospects/review")).toBe("leads");
  expect(id("/app/prospects/to-enrich")).toBe("leads");
  expect(id("/app/prospects/abc-123")).toBe("leads");
  expect(id("/app/batches")).toBe("batches");
  expect(id("/app/drafts")).toBe("outreach");
  expect(id("/app/campaigns")).toBe("outreach");
  expect(id("/app/settings/offer")).toBe("control");
  expect(id("/app/settings")).toBe("control");
  expect(id("/app/agents")).toBe("control");
  expect(id("/app/system")).toBe("control");
  expect(sectionOf("/login")).toBeNull();
});

test("activeNavItem resolves the correct destination for any route", () => {
  expect(activeNavItem("/app/dashboard").id).toBe("dashboard");
  expect(activeNavItem("/app/map").id).toBe("map");
  expect(activeNavItem("/app/leads").id).toBe("leads");
  expect(activeNavItem("/app/prospects").id).toBe("leads");
  expect(activeNavItem("/app/launch").id).toBe("campaigns");
  expect(activeNavItem("/app/analytics").id).toBe("analytics");
  expect(activeNavItem("/app/drafts").id).toBe("drafts");
  expect(activeNavItem("/app/agents").id).toBe("agents");
  expect(activeNavItem("/app/prospects/review").id).toBe("qualification");
  expect(activeNavItem("/app/settings/offer").id).toBe("offer");
  expect(activeNavItem("/app/system").id).toBe("system");
});

test("the current tab follows the path and the pipeline query", () => {
  const leads = SECTIONS.find((s) => s.id === "leads");
  expect(activeTab(leads, "/app/leads", "").label).toBe("CRM");
  expect(activeTab(leads, "/app/leads", "?view=kanban").label).toBe("Pipeline");
  expect(activeTab(leads, "/app/prospects/p1", "").label).toBe("Prospects");
});
