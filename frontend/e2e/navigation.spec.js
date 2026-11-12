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

const ENTRIES = '[data-testid="sidebar"] nav > ul > li > a[data-testid^="nav-"]';

test("the sidebar is six entries, all in view without scrolling, from a tall desktop down to a low and zoomed one", async ({ page }) => {
  await signIn(page);
  // /app/drafts is the worst case: Outreach is the section with the most screens listed under it
  for (const path of ["/app/dashboard", "/app/drafts"]) {
    for (const size of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1280, height: 560 }, { width: 1024, height: 480 }]) {
      await page.setViewportSize(size);
      await page.goto(path);
      const links = page.locator(ENTRIES);
      await expect(links).toHaveText(SIX);
      for (let i = 0; i < SIX.length; i++) await inside(page, links.nth(i)); // not hidden, not pushed below the fold
      for (const tool of ["open-palette", "open-ai-composer", "sidebar-toggle", "logout-button"]) await inside(page, page.getByTestId(tool));
      const nav = page.getByTestId("sidebar").locator("nav");
      expect(await nav.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true); // the list itself never needs a scrollbar
    }
  }
});

test("there is no top bar: the page starts at the top of the window, and the logo is centred in the sidebar, open or folded", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await expect(page.getByTestId("section-bar")).toHaveCount(0);
  await expect(page.getByTestId("section-tabs")).toHaveCount(0);
  expect((await page.getByTestId("main").boundingBox()).y).toBe(0); // nothing above the content on a desktop
  const centred = async () => {
    const side = await page.getByTestId("sidebar").boundingBox();
    const logo = await page.getByTestId("brand").locator("a").boundingBox();
    expect(Math.abs(logo.x + logo.width / 2 - (side.x + side.width / 2))).toBeLessThanOrEqual(1.5);
  };
  await centred();
  await expect(page.getByTestId("brand")).toContainText("PLANTIERS");
  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true");
  await expect(page.getByTestId("sidebar-toggle")).toHaveAttribute("aria-expanded", "false");
  await page.waitForTimeout(350); // the 200 ms width transition
  await centred();
  await expect(page.getByTestId("brand")).not.toContainText("PLANTIERS"); // the compact mark alone
  expect((await page.getByTestId("sidebar").boundingBox()).width).toBeLessThan(80);
});

test("every section opens its first screen and lists the others under it; the old direct routes still work", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  const sections = [
    ["nav-prospecting", /\/app\/map$/, ["tab-map", "tab-sources", "tab-import"]],
    ["nav-leads", /\/app\/leads$/, ["tab-crm", "tab-pipeline", "tab-prospects", "tab-review", "tab-to-enrich"]],
    ["nav-batches", /\/app\/batches$/, ["tab-batches"]],
    ["nav-outreach", /\/app\/drafts$/, ["tab-drafts", "tab-journey", "tab-launch", "tab-campaigns", "tab-messages", "tab-sending"]],
    ["nav-control", /\/app\/settings$/, ["tab-offer", "tab-settings", "tab-agents", "tab-automation-max", "tab-system"]],
    ["nav-overview", /\/app\/dashboard$/, ["tab-dashboard", "tab-analytics"]],
  ];
  for (const [entry, url, tabs] of sections) {
    await page.getByTestId(entry).click();
    await expect(page).toHaveURL(url);
    await expect(page.getByTestId("subnav").locator("a")).toHaveCount(tabs.length); // these screens and no other
    for (const tab of tabs) await expect(page.getByTestId(tab)).toBeVisible();
  }
  await page.getByTestId("nav-leads").click();
  await page.getByTestId("tab-pipeline").click();
  await expect(page).toHaveURL(/\/app\/leads\?view=kanban$/);
  await expect(page.getByTestId("tab-pipeline")).toHaveAttribute("aria-current", "page");
  for (const route of ["/app/campaigns", "/app/messages", "/app/sending", "/app/agents", "/app/analytics", "/app/system", "/app/sources", "/app/prospects", "/app/prospects/review", "/app/prospects/import", "/app/prospects/to-enrich", "/app/settings/offer", "/app/launch", "/app/journey", "/app/automation-max"]) {
    await page.goto(route);
    await expect(page.locator('[data-testid="subnav"] a[aria-current="page"]')).toHaveCount(1); // a direct route lands inside its section, its screen marked
  }
});

test("what the top bar held is still one action away: the AI composer, and every screen through the go-to palette", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await page.getByTestId("open-ai-composer").click();
  await expect(page.getByTestId("ai-composer-modal")).toBeVisible();
  await page.getByTestId("close-ai-composer").click();
  await expect(page.getByTestId("ai-composer-modal")).toHaveCount(0);

  await page.getByTestId("sidebar-toggle").click(); // folded: the screens are not listed, the palette reaches them
  await expect(page.getByTestId("subnav")).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await expect(page.getByTestId("palette-input")).toBeFocused();
  await page.getByTestId("palette-input").fill("enrichir");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/prospects\/to-enrich$/);
  await expect(page.getByTestId("palette-input")).toHaveCount(0);
  await page.getByTestId("open-palette").click(); // and by the button, with its accessible name
  await page.getByTestId("palette-input").fill("Automatisation max");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/automation-max$/);
  await page.keyboard.press("Control+k");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("palette-input")).toHaveCount(0);
});

test("folded, the six entries stay reachable by name with a tooltip, and the mobile drawer offers the same six with focus kept", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true");
  await expect(page.getByRole("link", { name: "Prospection" })).toBeVisible();
  await page.getByTestId("nav-prospecting").focus(); // the tooltip answers the keyboard, not only the mouse
  await expect(page.getByRole("tooltip")).toHaveText("Prospection");
  await page.getByRole("link", { name: "Batches" }).click();
  await expect(page).toHaveURL(/\/app\/batches$/);
  await page.reload();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true"); // the choice is remembered

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/dashboard");
  await page.getByTestId("mobile-nav-toggle").click();
  const drawer = page.getByRole("dialog", { name: "Navigation mobile" });
  await expect(drawer).toBeVisible();
  await expect(drawer.locator('nav > ul > li > a[data-testid^="mobile-nav-"]')).toHaveText(SIX);
  await expect(drawer.getByLabel("Fermer la navigation")).toBeFocused();
  await expect(drawer.getByTestId("mobile-open-ai-composer")).toBeVisible();
  await drawer.getByTestId("mobile-nav-control").click();
  await expect(page).toHaveURL(/\/app\/settings$/);
  await expect(page.getByTestId("mobile-drawer")).toHaveCount(0);
  await page.getByTestId("mobile-nav-toggle").click();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("mobile-nav-toggle")).toBeFocused();
  // on a phone the screens of the section are in the drawer, none cut off or unreachable
  await page.goto("/app/prospects");
  await page.getByTestId("mobile-nav-toggle").click();
  await page.getByTestId("mobile-tab-to-enrich").click();
  await expect(page).toHaveURL(/\/app\/prospects\/to-enrich$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no sideways scroll
});

test("keyboard: Tab goes through the six entries in order, the screens of the current one right after it, and Enter opens one", async ({ page }) => {
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await page.getByTestId("brand").locator("a").focus();
  const order = [];
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    order.push(await page.evaluate(() => document.activeElement.getAttribute("data-testid")));
  }
  expect(order).toEqual(["nav-overview", "tab-dashboard", "tab-analytics", "nav-prospecting", "nav-leads", "nav-batches", "nav-outreach", "nav-control"]);
  await page.getByTestId("nav-batches").focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/batches$/);
});

test("reduced motion: the sidebar folds without a transition", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  const moving = await page.getByTestId("sidebar").evaluate((el) => window.getComputedStyle(el).transitionProperty);
  expect(moving).toBe("none"); // nothing is animated: the width changes at once
  const label = await page.getByTestId("nav-leads").locator("span.shell-label").evaluate((el) => window.getComputedStyle(el).animationName);
  expect(label).toBe("none");
});
