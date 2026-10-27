import { pageOf, pages, prefetch, prefetchPath } from "@/lib/routes";

test("an in-app path names the screen behind it, query and trailing slash ignored", () => {
  expect(pageOf("/app/leads?view=kanban")).toBe("leads");
  expect(pageOf("/app/prospects/review/")).toBe("review");
  expect(pageOf("/app/prospects/import")).toBe("prospectImport");
  expect(pageOf("/app/map?city=Lyon")).toBe("map");
  expect(pageOf("/login")).toBeNull();
  expect(pageOf(undefined)).toBeNull();
});

test("every path of the navigation has a screen to warm up", () => {
  const nav = ["dashboard", "map", "sources", "prospects", "review", "leads", "campaigns", "messages", "sending", "agents", "analytics", "system", "settings"];
  nav.forEach((name) => expect(typeof pages[name]).toBe("function"));
});

test("a screen is asked for once, and an unknown one never", () => {
  const original = pages.dashboard;
  pages.dashboard = jest.fn(() => Promise.resolve({}));
  prefetch("dashboard");
  prefetch("dashboard");
  prefetchPath("/app/dashboard");
  expect(pages.dashboard).toHaveBeenCalledTimes(1);
  expect(() => { prefetch("nope"); prefetch(null); prefetchPath("/elsewhere"); }).not.toThrow();
  pages.dashboard = original;
});

test("a failed warm-up is forgotten so the next one can retry", async () => {
  const original = pages.campaigns;
  pages.campaigns = jest.fn(() => Promise.reject(new Error("offline")));
  prefetch("campaigns");
  await Promise.resolve();
  await Promise.resolve();
  prefetch("campaigns");
  expect(pages.campaigns).toHaveBeenCalledTimes(2);
  pages.campaigns = original;
});
