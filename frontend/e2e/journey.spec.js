// The complete journey a human follows, through the UI, against the real API:
// register → empty dashboard → discovery → review → draft → approve → dispatch (dry-run) → STOP reply → dashboard.
const { test, expect } = require("@playwright/test");

const API = process.env.E2E_API_URL || "http://localhost:8000";
const uid = () => Math.random().toString(36).slice(2, 10);

async function register(page) {
  const id = uid();
  await page.goto("/register");
  await page.getByTestId("register-name-input").fill("E2E Tester");
  await page.getByTestId("register-org-input").fill(`E2E Org ${id}`);
  await page.getByTestId("register-email-input").fill(`e2e_${id}@test.example`);
  await page.getByTestId("register-password-input").fill(`Pw-${id}-xyz`);
  await page.getByTestId("register-submit-button").click();
  await expect(page).toHaveURL(/\/app\/dashboard/);
}

test("the legal pages and the footer are public and linked", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByTestId("app-footer")).toContainText("© Plantiers - Software Engineering");
  await page.getByTestId("footer-legal").click();
  await expect(page.getByTestId("page-legal")).toContainText("Directeur de la publication");
  await expect(page).toHaveTitle(/Mentions légales \| Plantiers - OutreachOS/);
  await page.getByTestId("footer-privacy").click();
  await expect(page.getByTestId("page-privacy")).toContainText("intérêt légitime");
  await page.getByTestId("footer-terms").click();
  await expect(page.getByTestId("page-terms")).toContainText("Usage autorisé");
  // The static head is what crawlers read.
  const html = await (await page.request.get("/")).text();
  expect(html).toContain("AI-powered lead generation for software agencies");
  expect(html).toContain('"@type": "SoftwareApplication"');
});

test("complete journey: discovery → review → draft → dry-run dispatch → STOP reply → dashboard", async ({ page }) => {
  await register(page);

  // 1. A new organisation sees honest empty states, not invented figures.
  await expect(page.getByTestId("kpi-avg_score-value")).toHaveText("—");
  await expect(page.getByTestId("kpi-prospects-value")).toHaveText("0");
  await expect(page.getByTestId("chart-empty")).toBeVisible();
  await expect(page.getByTestId("limits-mode")).toHaveText("DRY-RUN");

  // 2. Discovery from the fictional fixture directory (nothing leaves the process).
  await page.goto("/app/prospects");
  await page.getByTestId("empty-run-discovery").click();
  await expect(page.getByTestId("prospects-table")).toBeVisible();
  await page.getByRole("link", { name: /La Table d'Alice/ }).first().click();

  // 3. The score is explained, with signals and provenance.
  await expect(page.getByTestId("prospect-detail")).toBeVisible();
  await expect(page.getByTestId("score-breakdown")).toBeVisible();
  await expect(page.getByTestId("source-list")).toContainText("fixture_directory");

  // 4. Human review, then an evidence-only draft, approved by a human.
  await page.getByTestId("detail-approve").click();
  await expect(page.getByTestId("detail-status")).toContainText(/approved/i);
  await page.getByTestId("create-draft").click();
  await expect(page.getByTestId("draft-item")).toBeVisible();
  await expect(page.getByTestId("draft-body")).toContainText("ne plus recevoir"); // the unsubscribe notice is in the draft
  await page.getByTestId("approve-draft").click();

  // 5. Dispatch is a dry run: the message is recorded, nothing is delivered.
  await page.getByTestId("dispatch-draft").click();
  await page.goto("/app/sending");
  await expect(page.getByTestId("status-panel")).toContainText("Dry-run");
  await page.getByTestId("message-row").first().click();
  await expect(page.getByTestId("message-detail")).toContainText("dry run: true");
  await expect(page.getByTestId("message-detail")).toContainText("list unsubscribe: true");

  // 6. A STOP reply opts the prospect out.
  await page.getByTestId("simulate-text").fill("STOP");
  await page.getByTestId("simulate-reply").click();

  // 7. The dashboard reflects what really happened.
  await page.goto("/app/dashboard");
  await expect(page.getByTestId("kpi-prospects-value")).not.toHaveText("0");
  await expect(page.getByTestId("kpi-sent_today-value")).toHaveText("1");
  await expect(page.getByTestId("kpi-replies-value")).toHaveText("1");
  await expect(page.getByTestId("kpi-unsubscribed-value")).toHaveText("1");
  await expect(page.getByTestId("inbox-item").first()).toContainText("simulated");
  await expect(page.getByTestId("limits-quota")).toHaveText("1 / 20");
});

test("real sending stays closed by default: test-send and import refuse, and say why", async ({ page }) => {
  await register(page);
  await page.goto("/app/sending");
  await page.getByTestId("smtp-test-to").fill("founder@plantiers.com");
  await page.getByTestId("smtp-test-send").click();
  // 501 live_not_available, or 409 when this server has no sender identity: either way nothing was sent.
  await expect(page.getByTestId("smtp-test-error")).toContainText(/not available|not configured|FEATURE_LIVE_SENDING|sender identity/i);
  await page.goto("/app/prospects/import");
  await expect(page.getByTestId("import-disabled")).toContainText("FEATURE_PROSPECT_IMPORT");
});

test("the pause switch on the dashboard stops sending and is reversible", async ({ page }) => {
  await register(page);
  await page.getByTestId("limits-toggle-pause").click();
  await expect(page.getByTestId("limits-mode")).toHaveText("PAUSED");
  const token = await page.evaluate(() => localStorage.getItem("outreachos_token"));
  const refused = await page.request.post(`${API}/api/messages/email`, {
    headers: { authorization: `Bearer ${token}` },
    data: { to: "someone@test.example", subject: "s", body: "b" },
  });
  expect(refused.status()).toBe(423); // the legacy single send obeys the same pause
  await page.getByTestId("limits-toggle-pause").click();
  await expect(page.getByTestId("limits-mode")).toHaveText("DRY-RUN");
});

test("a visitor without a session is sent to the login page", async ({ page }) => {
  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
