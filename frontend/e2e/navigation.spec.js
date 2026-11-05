const { test, expect } = require("@playwright/test");

const SIX = ["Vue d’ensemble", "Prospection", "Leads", "Batches", "Outreach", "Pilotage"];
const signIn = async (page) => {
  await page.addInitScript(() => localStorage.setItem("outreachos_token", "isolated-navigation-test"));
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, json: { detail: "Isolated navigation test" } }));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: {
    user: { email: "navigation@example.test", role: "owner" },
    organization: { name: "Navigation test", plan: "pro" },
  } }));
};
const inside = async (page, locator) => {
  const box = await locator.boundingBox();
  const view = page.viewportSize();
  expect(box).not.toBeNull();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(view.height);
};

test("the sidebar is six entries, all in view without scrolling, from a tall desktop down to a low and zoomed one", async ({ page }) => {
  await signIn(page);
  for (const size of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1280, height: 560 }, { width: 1024, height: 480 }]) {
    await page.setViewportSize(size);
    await page.goto("/app/dashboard");
    const links = page.getByTestId("sidebar").locator("nav a");
    await expect(links).toHaveText(SIX);
    for (let i = 0; i < SIX.length; i++) await inside(page, links.nth(i)); // not hidden, not pushed below the fold
    await inside(page, page.getByTestId("logout-button"));
    const nav = page.getByTestId("sidebar").locator("nav");
    expect(await nav.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true); // the list itself never needs a scrollbar
  }
});

test("every section opens its first screen and its tabs reach the others; the old direct routes still work", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  const sections = [
    ["nav-prospecting", /\/app\/map$/, ["tab-map", "tab-sources", "tab-import"]],
    ["nav-leads", /\/app\/leads$/, ["tab-crm", "tab-pipeline", "tab-prospects", "tab-review", "tab-to-enrich"]],
    ["nav-batches", /\/app\/batches$/, ["tab-batches"]],
    ["nav-outreach", /\/app\/drafts$/, ["tab-drafts", "tab-launch", "tab-campaigns", "tab-messages", "tab-sending"]],
    ["nav-control", /\/app\/settings$/, ["tab-offer", "tab-settings", "tab-agents", "tab-system"]],
    ["nav-overview", /\/app\/dashboard$/, ["tab-dashboard", "tab-analytics"]],
  ];
  for (const [entry, url, tabs] of sections) {
    await page.getByTestId(entry).click();
    await expect(page).toHaveURL(url);
    for (const tab of tabs) await expect(page.getByTestId(tab)).toBeVisible();
  }
  await page.getByTestId("nav-leads").click();
  await page.getByTestId("tab-pipeline").click();
  await expect(page).toHaveURL(/\/app\/leads\?view=kanban$/);
  await expect(page.getByTestId("tab-pipeline")).toHaveAttribute("aria-current", "page");
  for (const route of ["/app/campaigns", "/app/messages", "/app/sending", "/app/agents", "/app/analytics", "/app/system", "/app/sources", "/app/prospects", "/app/prospects/review", "/app/prospects/import", "/app/prospects/to-enrich", "/app/settings/offer", "/app/launch"]) {
    await page.goto(route);
    await expect(page.getByTestId("section-bar")).toBeVisible(); // a direct route lands inside its section, with its tabs
  }
});

test("folded, the six entries stay reachable by name, and the mobile drawer offers the same six with focus kept", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true");
  await expect(page.getByRole("link", { name: "Prospection" })).toBeVisible();
  await page.getByRole("link", { name: "Batches" }).click();
  await expect(page).toHaveURL(/\/app\/batches$/);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/dashboard");
  await page.getByTestId("mobile-nav-toggle").click();
  const drawer = page.getByRole("dialog", { name: "Navigation mobile" });
  await expect(drawer).toBeVisible();
  await expect(drawer.locator("nav a")).toHaveText(SIX);
  await expect(drawer.getByLabel("Fermer la navigation")).toBeFocused();
  await drawer.getByTestId("mobile-nav-control").click();
  await expect(page).toHaveURL(/\/app\/settings$/);
  await expect(page.getByTestId("mobile-drawer")).toHaveCount(0);
  await page.getByTestId("mobile-nav-toggle").click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("mobile-nav-toggle")).toBeFocused();
  // the tabs of the section scroll sideways on a phone: none is cut off or unreachable
  await page.goto("/app/prospects");
  await page.getByTestId("tab-to-enrich").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("tab-to-enrich")).toBeVisible();
});

test("keyboard: Tab reaches the six entries in order and Enter opens one", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await page.getByTestId("sidebar-toggle").focus();
  const order = [];
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    order.push(await page.evaluate(() => document.activeElement.textContent));
  }
  expect(order).toEqual(SIX);
  await page.getByTestId("nav-batches").focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/batches$/);
});
