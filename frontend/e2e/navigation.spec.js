const { test, expect } = require("@playwright/test");

test("grouped navigation stays reachable when folded and in the mobile drawer", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("outreachos_token", "isolated-navigation-test"));
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, json: { detail: "Isolated navigation test" } }));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: {
    user: { email: "navigation@example.test", role: "owner" },
    organization: { name: "Navigation test", plan: "pro" },
  } }));

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app/dashboard");
  await expect(page.getByTestId("sidebar")).toBeVisible();
  await expect(page.getByTestId("nav-dashboard")).toBeVisible();
  await page.getByTestId("nav-group-prospecting").click();
  await expect(page.getByTestId("nav-group-prospecting")).toHaveAttribute("aria-expanded", "true");

  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true");
  await page.getByTestId("nav-group-prospecting").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "false");
  await page.getByTestId("nav-map-search").click();
  await expect(page).toHaveURL(/\/app\/map$/);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/dashboard");
  await page.getByTestId("mobile-nav-toggle").click();
  const drawer = page.getByRole("dialog", { name: "Navigation mobile" });
  await expect(drawer).toBeVisible();
  await drawer.getByTestId("mobile-nav-group-control").click();
  await expect(drawer.getByTestId("mobile-nav-settings")).toBeVisible();
  await drawer.getByTestId("mobile-nav-settings").click();
  await expect(page).toHaveURL(/\/app\/settings$/);
  await expect(page.getByTestId("mobile-drawer")).toHaveCount(0);
});
