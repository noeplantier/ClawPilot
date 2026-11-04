const { test, expect } = require("@playwright/test");

// The sign-in page needs no API: it must frame the form well on every screen, and never shows a status it cannot know.
const centre = async (locator) => {
  const box = await locator.boundingBox();
  return { x: box.x + box.width / 2, y: box.y + box.height / 2, box };
};

test("login: the card is centred when the height allows, with the fields a password manager looks for", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/login");
  const card = page.getByTestId("login-form").locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");
  const c = await centre(card);
  expect(Math.abs(c.x - 640)).toBeLessThan(2); // not shifted by a sidebar or a column
  expect(Math.abs(c.y - 400)).toBeLessThan(60); // in the middle of the height
  await expect(page.locator('input[name="username"][autocomplete="username"]')).toBeVisible();
  await expect(page.locator('input[name="password"][autocomplete="current-password"]')).toBeVisible();
  const text = await page.locator("body").innerText();
  for (const claim of ["ONLINE", "v2.4", "verified"]) expect(text).not.toContain(claim);
});

test("login: a short screen or a phone keyboard scrolls the page, nothing is clipped, nothing overflows sideways", async ({ page }) => {
  for (const size of [{ width: 1280, height: 480 }, { width: 390, height: 320 }, { width: 320, height: 568 }]) {
    await page.setViewportSize(size);
    await page.goto("/login");
    const submit = page.getByTestId("login-submit-button");
    await submit.scrollIntoViewIfNeeded();
    await expect(submit).toBeVisible();
    await expect(page.getByTestId("goto-register-link")).toBeAttached();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.evaluate(() => window.scrollTo(0, 0));
    const top = await centre(page.getByTestId("brand-logo"));
    expect(top.box.y).toBeGreaterThanOrEqual(0); // back at the top, the logo is where it belongs: not pushed above the page
  }
});

test("register shares the frame of login and labels every field", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/register");
  for (const [label, auto] of [["operator.name", "name"], ["organization", "organization"], ["email", "username"], ["password", "new-password"]]) {
    const field = page.getByLabel(label, { exact: true });
    await expect(field).toBeVisible();
    await expect(field).toHaveAttribute("autocomplete", auto);
  }
  const c = await centre(page.getByTestId("register-form").locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"));
  expect(Math.abs(c.x - 640)).toBeLessThan(2);
});

test("login: the reduced-motion preference removes the entrance animation", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("/login");
  await expect(page.getByTestId("login-form")).toBeVisible();
  const opacity = await page.getByTestId("auth-main").locator("> div").evaluate((el) => getComputedStyle(el).opacity);
  expect(opacity).toBe("1"); // visible at once: no fade to wait for
  await context.close();
});
