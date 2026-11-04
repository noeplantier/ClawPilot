/* global require, __dirname */
import { SECTIONS, activeTab, pathOf, sectionOf } from "@/lib/sections";

const fs = require("fs");
const path = require("path");

// Every path declared under <Route path="/app"> in App.js, with the dynamic ones given a sample value.
const appRoutes = () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "App.js"), "utf8");
  const inside = source.slice(source.indexOf('path="/app"'), source.indexOf('path="*"'));
  return [...inside.matchAll(/<Route\s+(?:index\s+)?path="([^"]+)"/g)].map((m) => `/app/${m[1].replace(":id", "p1")}`);
};

test("the sidebar has exactly six sections, in the order of the brief, each with a way in", () => {
  expect(SECTIONS.map((s) => s.label)).toEqual(["Vue d’ensemble", "Prospection", "Leads", "Batches", "Outreach", "Pilotage"]);
  expect(new Set(SECTIONS.map((s) => s.id)).size).toBe(6);
  for (const s of SECTIONS) {
    expect(s.tabs.length).toBeGreaterThan(0);
    expect(s.tabs.some((t) => pathOf(t.to) === pathOf(s.to))).toBe(true); // the sidebar link is one of the tabs
  }
});

test("every screen of the application belongs to a section: nothing useful is unreachable", () => {
  const routes = appRoutes();
  expect(routes.length).toBeGreaterThan(14);
  const orphans = routes.filter((r) => !sectionOf(r));
  expect(orphans).toEqual([]);
});

test("every tab leads to a screen that exists", () => {
  const known = new Set(appRoutes().map(pathOf));
  const missing = SECTIONS.flatMap((s) => s.tabs).map((t) => pathOf(t.to)).filter((p) => !known.has(p));
  expect(missing).toEqual([]);
});

test("a path lands in the section that holds it, the nested screen under its own tab", () => {
  const id = (p) => (sectionOf(p) || {}).id;
  expect(id("/app/dashboard")).toBe("overview");
  expect(id("/app/analytics")).toBe("overview");
  expect(id("/app/map")).toBe("prospecting");
  expect(id("/app/prospects/import")).toBe("prospecting"); // longer than /app/prospects, which is Leads
  expect(id("/app/prospects")).toBe("leads");
  expect(id("/app/prospects/review")).toBe("leads");
  expect(id("/app/prospects/to-enrich")).toBe("leads");
  expect(id("/app/prospects/abc-123")).toBe("leads"); // a prospect's sheet
  expect(id("/app/batches")).toBe("batches");
  expect(id("/app/drafts")).toBe("outreach");
  expect(id("/app/campaigns")).toBe("outreach");
  expect(id("/app/settings/offer")).toBe("control");
  expect(id("/app/settings")).toBe("control");
  expect(id("/app/agents")).toBe("control");
  expect(id("/app/system")).toBe("control");
  expect(sectionOf("/login")).toBeNull();
});

test("the current tab follows the path and the pipeline query", () => {
  const leads = SECTIONS.find((s) => s.id === "leads");
  expect(activeTab(leads, "/app/leads", "").label).toBe("CRM");
  expect(activeTab(leads, "/app/leads", "?view=kanban").label).toBe("Pipeline");
  expect(activeTab(leads, "/app/prospects/p1", "").label).toBe("Prospects"); // a sheet keeps its list highlighted
  expect(activeTab(leads, "/app/prospects/review", "").label).toBe("À vérifier");
  const control = SECTIONS.find((s) => s.id === "control");
  expect(activeTab(control, "/app/settings/offer", "").label).toBe("Offre");
  expect(activeTab(control, "/app/settings", "").label).toBe("Intégrations et réglages");
  expect(activeTab(null, "/x")).toBeNull();
});
