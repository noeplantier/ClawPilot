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

test("the map shows real places from the search, marks what is published and never invents a contact", async ({ page }) => {
  // The server runs with the flags off (the safe default): the page says so. Then the flag and OpenStreetMap are faked
  // at the network edge so the interactive map can be exercised without any outside access.
  await register(page);
  await page.goto("/app/map");
  await expect(page.getByTestId("map-disabled")).toContainText("FEATURE_EXTERNAL_SOURCES");

  await page.route("**/api/prospects/settings", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, flags: { ...real.flags, external_sources: true, prospect_import: false } } });
  });
  await page.route(/(tile\.openstreetmap\.org|basemaps\.cartocdn\.com)/, (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64") }));
  await page.route("**/api/map/prospects", (route) =>
    route.fulfill({
      json: [
        { id: "p1", name: "Chez Marcel", city: "Lyon", lat: 45.7641, lon: 4.8358, review_status: "pending", has_email: true, external_id: "node/1" },
        { id: "p2", name: "Déjà prospect", city: "Lyon", lat: 45.762, lon: 4.83, review_status: "approved", has_email: false, external_id: null },
      ],
    }));
  // The search is a persisted job: create, poll (queued -> running -> succeeded), read the places. The API is faked at the network edge.
  const PLACES = {
    attribution: "© OpenStreetMap contributors (ODbL)", license_note: "ODbL", truncated: false,
    places: [
      { external_id: "node/1", name: "Chez Marcel", category: "restaurant", lat: 45.7641, lon: 4.8358, address: "12 Rue Merciere", postcode: "69002", city: "Lyon", phone: "+33 4 78 12 34 56", email: "contact@chez-marcel.example", website: "https://chez-marcel.example", source_url: "https://www.openstreetmap.org/node/1" },
      { external_id: "way/2", name: "Boulangerie Martin", category: "bakery", lat: 45.7601, lon: 4.8401, address: null, postcode: null, city: null, phone: null, email: null, website: null, source_url: "https://www.openstreetmap.org/way/2" },
    ],
  };
  const job = (status, extra = {}) => ({ id: "j1", status, category: "restaurants", south: 45.75, west: 4.82, north: 45.77, east: 4.85, source: "overpass", result_count: 0, truncated: false, cache_hit: false, error_code: null, error: null, duration_ms: null, created_at: "2026-10-23T10:00:00Z", started_at: null, finished_at: null, fallback: null, ...extra });
  let polls = 0;
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill(route.request().method() === "POST" ? { status: 202, json: job("queued") } : { json: [] }));
  await page.route("**/api/map/search/j1", (route) => {
    polls += 1;
    return route.fulfill({ json: polls < 2 ? job("running") : job("succeeded", { result_count: 2, duration_ms: 900 }) });
  });
  await page.route("**/api/map/search/j1/places", (route) => route.fulfill({ json: PLACES }));
  await page.goto("/app/map");
  await expect(page.getByTestId("map")).toBeVisible();
  await expect(page.getByTestId("map-empty")).toBeVisible();
  await page.getByTestId("map-search").click();
  await expect(page.getByTestId("map-job")).toContainText("2 places saved from OpenStreetMap");
  // "Chez Marcel" is already one of my prospects: it is drawn as a prospect (square), not offered again as a search result.
  await expect(page.getByTestId("map-mine-toggle")).toContainText("2 prospects on the map: 1 to review, 1 approved, 0 rejected");
  await expect(page.getByTestId("map-summary")).toHaveText("1 place: 0 with a published e-mail, 0 with a phone, 0 with a website.");
  await expect(page.locator(".map-pin")).toHaveCount(3); // 2 of my prospects + 1 new place
  await page.locator(".map-pin").nth(2).dispatchEvent("click"); // the search result (drawn last)
  await expect(page.locator(".leaflet-popup-content")).toContainText("source on OpenStreetMap");
  await page.getByTestId("map-select-all").click();
  await expect(page.getByTestId("map-import-off")).toContainText("FEATURE_PROSPECT_IMPORT"); // import stays closed without its flag
});

test("sources: discover from the world demo, see explained signals, page, add to the review queue; live sources say why they are off", async ({ page }) => {
  await register(page);
  await page.getByTestId("nav-sources").click();
  await expect(page.getByTestId("sources-page")).toBeVisible();
  // The server runs with the flags off: live providers are shown but disabled, with the reason.
  await expect(page.getByTestId("source-openstreetmap-off")).toContainText("FEATURE_EXTERNAL_SOURCES");
  await expect(page.getByTestId("source-registry_fr-off")).toContainText("FEATURE_EXTERNAL_SOURCES");

  await page.getByTestId("source-limit").fill("30");
  await page.getByTestId("source-discover").click();
  await expect(page.getByTestId("source-summary")).toContainText("places");
  await expect(page.getByTestId("source-summary")).toContainText("Fictional data");
  const rows = page.locator('[data-testid^="place-wf-"]');
  await expect(rows.first()).toBeVisible();
  await expect(rows.first()).toContainText("unknown"); // signals are explained and "unknown" stays unknown
  const firstPage = await rows.count();
  expect(firstPage).toBeGreaterThan(0);

  if (await page.getByTestId("source-next").isEnabled()) {
    await page.getByTestId("source-next").click();
    await expect(page.getByTestId("source-range")).toContainText("26");
    await page.getByTestId("source-prev").click();
  }

  await rows.first().getByRole("checkbox").check();
  await rows.nth(1).getByRole("checkbox").check();
  await expect(page.getByTestId("source-add")).toContainText("Add 2 to prospects");
  await expect(page.getByTestId("source-add-run")).toBeDisabled(); // not before the attestation
  await page.getByTestId("source-attest").check();
  await page.getByTestId("source-add-run").click();
  await expect(page.getByTestId("source-add-done")).toContainText("2 added");
  await page.goto("/app/prospects");
  await expect(page.getByTestId("prospect-row")).toHaveCount(2); // the two places added from the demo
});

test("the prospects map clusters nearby prospects, filters them, refreshes by polling and starts a campaign from the selection", async ({ page }) => {
  await register(page);
  await page.route("**/api/prospects/settings", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, flags: { ...real.flags, external_sources: true, prospect_import: false } } });
  });
  await page.route(/(tile\.openstreetmap\.org|basemaps\.cartocdn\.com)/, (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64") }));
  const base = { has_email: false, external_id: null, country: "FR", created_at: "2026-10-03T10:00:00Z" };
  const rows = [
    { ...base, id: "a1", name: "Boulangerie Un", city: "Lyon", lat: 45.7641, lon: 4.8358, review_status: "approved", vertical: "bakery", score: 70, signals: ["no_website"] },
    { ...base, id: "a2", name: "Boulangerie Deux", city: "Lyon", lat: 45.7643, lon: 4.8361, review_status: "pending", vertical: "bakery", score: null, signals: [] },
    { ...base, id: "a3", name: "Hôtel Trois", city: "Lyon", lat: 45.7642, lon: 4.8359, review_status: "approved", vertical: "hotel", score: 40, signals: ["outdated_technology"] },
    { ...base, id: "a4", name: "Café Lointain", city: "Paris", lat: 48.8566, lon: 2.3522, review_status: "approved", vertical: "restaurant", score: 55, signals: [] },
  ];
  let polled = 0;
  await page.route("**/api/map/prospects", (route) => { polled += 1; return route.fulfill({ json: rows }); });
  let assigned = null;
  await page.route("**/api/campaigns", (route) =>
    route.request().method() === "POST" ? route.fulfill({ json: { id: "c-map", name: "Map selection" } }) : route.continue());
  await page.route("**/api/campaigns/c-map/assign-leads", (route) => { assigned = route.request().postDataJSON(); return route.fulfill({ json: { id: "c-map" } }); });

  await page.goto("/app/map");
  await expect(page.getByTestId("filter-summary")).toHaveText("4 prospects on the map.");
  await expect(page.locator(".map-cluster")).toHaveText("3"); // the three Lyon prospects merge; Paris is out of view
  await page.getByTestId("filter-vertical").selectOption("hotel");
  await expect(page.getByTestId("filter-summary")).toHaveText("1 of 4 prospects match the filters.");
  await expect(page.locator(".map-cluster")).toHaveCount(0);
  await page.getByTestId("filter-vertical").selectOption("");
  await page.getByTestId("filter-score").fill("50");
  await expect(page.getByTestId("filter-summary")).toHaveText("2 of 4 prospects match the filters."); // "not scored" never passes a threshold
  await page.getByTestId("filter-clear").click();

  await page.locator(".map-cluster").dispatchEvent("click");
  await expect(page.getByTestId("map-mine-list")).toContainText("Cluster · 3 prospects");
  await expect(page.getByTestId("map-mine-list")).toContainText("not scored");
  await page.getByTestId("mine-row").nth(0).getByRole("checkbox").check();
  await page.getByTestId("mine-row").nth(1).getByRole("checkbox").check();
  await expect(page.getByTestId("start-campaign-note")).toContainText("not approved");
  await page.getByTestId("start-campaign").click();
  await expect(page).toHaveURL(/\/app\/campaigns/);
  expect(assigned.lead_ids.length).toBe(1); // only the approved one is sent to the API
  expect(polled).toBeGreaterThan(0);
});

test("a reviewer dismisses a wrong signal: it reads as unknown, the score is recomputed and the decision is reversible", async ({ page }) => {
  await register(page);
  await page.goto("/app/prospects");
  await page.getByTestId("empty-run-discovery").click();
  await page.getByRole("link", { name: /Le Petit Bouchon/ }).first().click();
  const before = await page.getByTestId("score-badge").first().innerText();
  await page.getByTestId("dismiss-no_website").click();
  await page.getByTestId("dismiss-confirm-no_website").isDisabled();
  await page.getByTestId("dismiss-reason-no_website").fill("They do have a site, the directory is old");
  await page.getByTestId("dismiss-confirm-no_website").click();
  await expect(page.getByTestId("dismissed-no_website")).toContainText("They do have a site");
  await expect(page.getByTestId("signal-no_website").getByTestId("state-unknown")).toBeVisible();
  const after = await page.getByTestId("score-badge").first().innerText();
  expect(after).not.toEqual(before); // the 30 points of this signal are gone
  await page.getByTestId("restore-no_website").click();
  await expect(page.getByTestId("signal-no_website").getByTestId("state-detected")).toBeVisible();
});

const MAP_STUBS = async (page) => {
  await page.route("**/api/prospects/settings", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, flags: { ...real.flags, external_sources: true, prospect_import: false } } });
  });
  await page.route(/(tile\.openstreetmap\.org|basemaps\.cartocdn\.com)/, (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64") }));
  await page.route("**/api/map/prospects", (route) => route.fulfill({ json: [] }));
};
const JOB = (status, extra = {}) => ({ id: "j9", status, category: "bakeries", south: 45.75, west: 4.82, north: 45.77, east: 4.85, source: "overpass", result_count: 0, truncated: false, cache_hit: false, error_code: null, error: null, duration_ms: null, created_at: "2026-10-23T10:00:00Z", started_at: null, finished_at: null, fallback: null, ...extra });
const ONE_PLACE = {
  attribution: "© OpenStreetMap contributors (ODbL)", license_note: "ODbL", truncated: false,
  places: [{ external_id: "node/7", name: "Boulangerie Sept", category: "bakery", lat: 45.76, lon: 4.835, address: null, postcode: null, city: "Lyon", phone: null, email: null, website: null, source_url: "https://www.openstreetmap.org/node/7" }],
};

test("when the server cannot reach OpenStreetMap the failed search is explained and the browser can complete it on request", async ({ page }) => {
  await register(page);
  await MAP_STUBS(page);
  let ingested = null;
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill(route.request().method() === "POST" ? { status: 202, json: JOB("queued") } : { json: [] }));
  await page.route("**/api/map/search/j9", (route) =>
    route.fulfill({ json: ingested ? JOB("succeeded", { source: "overpass_browser", result_count: 1 }) : JOB("failed", {
      error_code: "overpass_timeout", error: "The public OpenStreetMap servers did not answer in time. (overpass-api.de: TimeoutError)",
      fallback: { query: "[out:json];", endpoints: ["https://overpass.test/api/interpreter"] },
    }) }));
  await page.route("https://overpass.test/**", (route) =>
    route.fulfill({ headers: { "access-control-allow-origin": "*" }, json: { elements: [{ type: "node", id: 7, lat: 45.76, lon: 4.835, tags: { name: "Boulangerie Sept" } }] } }));
  await page.route("**/api/map/search/j9/ingest", (route) => { ingested = route.request().postDataJSON(); return route.fulfill({ json: JOB("succeeded", { source: "overpass_browser", result_count: 1 }) }); });
  await page.route("**/api/map/search/j9/places", (route) => route.fulfill({ json: ONE_PLACE }));

  await page.goto("/app/map");
  await page.getByTestId("map-search").click();
  await expect(page.getByTestId("map-job-failed")).toContainText("did not answer in time");
  await expect(page.getByTestId("map-job-failed")).toContainText("overpass_timeout"); // the cause is visible, not a blank 502
  await page.getByTestId("map-retry-browser").click();
  await expect(page.getByTestId("map-job")).toContainText("1 place saved through your browser");
  expect(ingested.data.elements).toHaveLength(1); // the browser's answer went to the server, which stores it
  await expect(page.getByTestId("map-summary")).toContainText("1 place");
});

test("the last finished search comes back from the database after a reload, without searching again", async ({ page }) => {
  await register(page);
  await MAP_STUBS(page);
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill({ json: [JOB("failed", { id: "jx" }), JOB("succeeded", { result_count: 1, duration_ms: 500 })] }));
  await page.route("**/api/map/search/j9/places", (route) => route.fulfill({ json: ONE_PLACE }));
  await page.goto("/app/map");
  await expect(page.getByTestId("map-job")).toContainText("1 place saved from OpenStreetMap in 0.5 s");
  await expect(page.getByTestId("map-summary")).toContainText("1 place");
  await expect(page.getByTestId("map-cat-bakeries")).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByTestId("map-job")).toContainText("1 place saved");
});

test("the system page reports the real database and migrations, and probes OpenStreetMap on request", async ({ page }) => {
  await register(page);
  await page.route("**/api/system/health/overpass", (route) =>
    route.fulfill({ json: { ok: false, servers: [{ host: "overpass-api.de", ok: false, error: "OSError: Network is unreachable", ms: 3 }] } }));
  await page.getByText("System health").first().click();
  await expect(page.getByTestId("system-page")).toBeVisible();
  await expect(page.getByTestId("health-database")).toHaveAttribute("data-ok", "true");
  await expect(page.getByTestId("health-migrations")).toHaveAttribute("data-ok", "true");
  await expect(page.getByTestId("health-jobs")).toContainText("No map search in the last 24 hours");
  await page.getByTestId("probe-run").click();
  await expect(page.getByTestId("probe-result")).toContainText("overpass-api.de: OSError: Network is unreachable");
  await expect(page.getByTestId("probe-result")).toContainText("None answered");
});

test("the sidebar folds and remembers it; the map has one real basemap and every panel can be closed or minimised", async ({ page }) => {
  await register(page);
  await MAP_STUBS(page);
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill(route.request().method() === "POST" ? { status: 202, json: JOB("succeeded", { id: "j9", result_count: 1 }) } : { json: [] }));
  await page.route("**/api/map/search/j9/places", (route) => route.fulfill({ json: ONE_PLACE }));

  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "false");
  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true");
  await page.reload();
  await expect(page.getByTestId("sidebar")).toHaveAttribute("data-folded", "true"); // remembered
  await page.getByTestId("nav-map-search").click(); // still reachable by its icon

  await expect(page.getByTestId("map")).toBeVisible();
  await expect(page.getByTestId("map-base-dark")).toHaveCount(0); // no light / dark variants
  await expect(page.getByTestId("map-base-light")).toHaveCount(0);

  await page.getByTestId("map-search").click();
  await expect(page.getByTestId("map-results")).toBeVisible();
  // minimise the search card to a pill: the search stays one click away
  await page.getByTestId("map-search-minimise").click();
  await expect(page.getByTestId("map-search-card")).toHaveCount(0);
  await expect(page.getByTestId("map-search-pill")).toBeVisible();
  await page.getByTestId("map-search-expand").click();
  await expect(page.getByTestId("map-search-card")).toBeVisible();
  // close the results panel, then bring it back
  await page.getByTestId("map-panel-close").click();
  await expect(page.getByTestId("map-panel-toggle")).toHaveAttribute("aria-expanded", "false");
  await page.getByTestId("map-panel-toggle").click();
  await expect(page.getByTestId("map-panel-toggle")).toHaveAttribute("aria-expanded", "true");
  // the whole map: every panel hidden with the button and with the H key
  await page.getByTestId("map-hide-panels").click();
  await expect(page.getByTestId("map-search-card")).toHaveCount(0);
  await expect(page.getByTestId("map-results")).toHaveCount(0);
  await page.getByTestId("map-hide-panels").click();
  await expect(page.getByTestId("map-search-card")).toBeVisible();
  await page.keyboard.press("h");
  await expect(page.getByTestId("map-search-card")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("map-search-card")).toBeVisible();
});

test("the import form of a map selection can be minimised and closed, so the whole map stays visible", async ({ page }) => {
  await register(page);
  await page.route("**/api/prospects/settings", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, flags: { ...real.flags, external_sources: true, prospect_import: true } } });
  });
  await page.route(/(tile\.openstreetmap\.org)/, (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64") }));
  await page.route("**/api/map/prospects", (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill(route.request().method() === "POST" ? { status: 202, json: JOB("succeeded", { id: "j9", result_count: 1 }) } : { json: [] }));
  await page.route("**/api/map/search/j9/places", (route) => route.fulfill({ json: ONE_PLACE }));
  await page.goto("/app/map");
  await page.getByTestId("map-search").click();
  await page.getByTestId("map-select-all").click();
  await expect(page.getByTestId("map-import")).toContainText("Import 1 selected place");
  await expect(page.getByTestId("map-attest")).toBeVisible();
  await page.getByTestId("import-minimise").click();
  await expect(page.getByTestId("map-attest")).toHaveCount(0); // minimised: only its title bar remains
  await expect(page.getByTestId("map-import")).toBeVisible();
  await page.getByTestId("import-minimise").click();
  await expect(page.getByTestId("map-attest")).toBeVisible();
  await page.getByTestId("import-close").click(); // closing clears the selection
  await expect(page.getByTestId("map-import")).toHaveCount(0);
});

async function apiPost(page, path, body) {
  const token = await page.evaluate(() => localStorage.getItem("outreachos_token"));
  const res = await page.request.post(`${process.env.E2E_API_URL || "http://localhost:8000"}/api${path}`, { headers: { Authorization: `Bearer ${token}` }, data: body });
  expect(res.status(), await res.text()).toBeLessThan(300);
  return res.json();
}

test("leads come hottest first with the real information behind the heat, and a new lead appears live", async ({ page }) => {
  await page.clock.install();
  await register(page);
  await apiPost(page, "/leads", { full_name: "A Name Only" });
  await apiPost(page, "/leads", { full_name: "B Rich Lead", email: "b@rich-lead.example", phone: "+33 4 78 00 00 01", company: "Rich SAS", title: "CEO", country: "FR" });
  await page.goto("/app/leads");
  const rows = page.locator('[data-testid^="lead-row-"]');
  // "A Name Only" has no e-mail, phone or website: it is empty, so it is left out and counted; one click brings it back
  await expect(rows).toHaveCount(1);
  await expect(page.getByTestId("leads-empty-toggle-note")).toHaveText("1 empty lead hidden (no e-mail, phone or website).");
  await expect(rows.first()).toContainText("B Rich Lead"); // the lead with the most real information is first
  await expect(rows.first().getByTestId("heat-badge")).toHaveAttribute("title", /5 of 8 real fields known/);
  await expect(rows.first().getByTestId("heat-badge")).toHaveAttribute("title", /Missing: website, city, category/);
  await expect(page.getByTestId("leads-live")).toContainText("Live · updated");
  await page.getByTestId("leads-empty-toggle").click();
  await expect(rows).toHaveCount(2);
  await expect(rows.last()).toContainText("e-mail not known"); // an unknown is shown as unknown

  // filter by tier
  const cold = page.getByTestId("lane-cold");
  const coldCount = Number((await cold.innerText()).replace(/\D/g, ""));
  expect(coldCount).toBeGreaterThanOrEqual(1);
  await cold.click();
  await expect(rows.first()).toContainText("A Name Only");
  await page.getByTestId("lane-all").click();

  // a lead created elsewhere shows up on the next refresh, flagged as new, and ranks by its information
  await apiPost(page, "/leads", { full_name: "C New Arrival", email: "c@arrival.example", phone: "+33 4 78 00 00 02", company: "Arrival SAS", title: "CTO", country: "FR" });
  await page.clock.fastForward(16000);
  await expect(page.getByTestId("lead-new")).toHaveCount(1);
  await expect(page.locator('[data-testid^="lead-row-"]', { hasText: "C New Arrival" })).toContainText("new");
  await expect(rows).toHaveCount(3);
});

test("the review queue is split into heat lanes counted by the server, hottest first, and says what is known", async ({ page }) => {
  await register(page);
  await apiPost(page, "/prospects/discovery/run", { source: "fixture_directory" });
  await page.goto("/app/prospects/review");
  await expect(page.getByTestId("queue-card")).toBeVisible();
  const n = async (key) => Number((await page.getByTestId(`queue-lane-${key}`).innerText()).replace(/\D/g, ""));
  const [all, hot, warm, cold] = [await n("all"), await n("hot"), await n("warm"), await n("cold")];
  expect(hot + warm + cold).toBe(all); // counted, never estimated
  expect(all).toBeGreaterThan(2);
  await expect(page.getByTestId("queue-lane-top")).toHaveText(/^TOP \d+$/); // the TOP lane (heat 80+) is counted by the server too
  await expect(page.getByTestId("queue-empty-toggle")).toHaveCount(0); // nothing is empty here: no control without a reason
  await expect(page.getByTestId("queue-live")).toContainText("Live · updated");
  await expect(page.getByTestId("queue-known")).toContainText("Known:");
  // the first card is the hottest one
  const firstTier = await page.getByTestId("queue-card").getByTestId("heat-badge").getAttribute("data-tier");
  const order = ["hot", "warm", "cold"];
  for (const lane of order.slice(0, order.indexOf(firstTier))) expect(await n(lane)).toBe(0); // nothing hotter is waiting
  // pick a lane that has prospects: the card follows
  for (const lane of ["hot", "warm", "cold"]) {
    if ((await n(lane)) === 0) continue;
    await page.getByTestId(`queue-lane-${lane}`).click();
    await expect(page.getByTestId("queue-card").getByTestId("heat-badge")).toHaveAttribute("data-tier", lane);
  }
  await page.getByTestId("queue-lane-all").click();
  if (all > 1) {
    await expect(page.getByTestId("queue-next")).toBeVisible();
    const next = page.getByTestId("queue-next-row").first();
    const name = (await next.locator(".font-medium").innerText()).replace(/\s*new$/i, "").trim();
    await page.getByTestId("queue-open-next").first().click(); // "review now" pins that prospect
    await expect(page.getByTestId("queue-name")).toHaveText(name);
  }
});

test("campaign suggestions come from the real data, update on their own, and create a draft that sends nothing", async ({ page }) => {
  await page.clock.install();
  await register(page);
  await page.goto("/app/campaigns");
  await expect(page.getByTestId("suggestions-empty")).toContainText("No suggestion yet"); // nothing invented for an empty organisation

  await apiPost(page, "/leads", { full_name: "Alice New", email: "alice@new.example", company: "Alice SAS" });
  await apiPost(page, "/leads", { full_name: "Bob New", phone: "+33 4 78 00 00 03", company: "Bob SAS" });
  await page.clock.fastForward(16000); // the next refresh
  const card = page.getByTestId("suggestion").first();
  await expect(card).toContainText("New leads still waiting for a first message");
  await expect(card.getByTestId("suggestion-new")).toBeVisible();
  await expect(card.getByTestId("suggestion-ready")).toHaveText("2 of 2 can join a campaign today");
  await expect(page.getByTestId("suggestions-basis")).toContainText("Computed from 0 prospects and 2 CRM leads");

  await apiPost(page, "/leads", { full_name: "Cleo New", email: "cleo@new.example", company: "Cleo SAS" });
  // Playwright's clock can apply a jump late, which leaves the next poll further away than one more jump (seen in ~10% of
  // runs): retry the jump until the page has polled, instead of assuming one jump equals one poll.
  await expect(async () => {
    await page.clock.fastForward(16000);
    await expect(page.getByTestId("suggestion").first().getByTestId("suggestion-ready")).toHaveText("3 of 3 can join a campaign today", { timeout: 3000 });
  }).toPass({ timeout: 30000 });

  await page.getByTestId("suggestion-create").first().click();
  await expect(page.locator('[data-testid^="campaign-card-"]').first()).toContainText("New leads still waiting for a first message");
  await expect(page.locator('[data-testid^="campaign-card-"]').first()).toContainText("draft");
});

test("suggestions for discovery prospects say why no campaign can start yet instead of offering a dead button", async ({ page }) => {
  await register(page);
  await apiPost(page, "/prospects/discovery/run", { source: "fixture_directory" });
  await page.goto("/app/campaigns");
  const first = page.getByTestId("suggestion").first();
  await expect(first).toBeVisible();
  await expect(first.getByTestId("suggestion-ready")).toContainText("dry-run");
  await expect(first.getByTestId("suggestion-create")).toBeDisabled();
  await expect(first.getByTestId("suggestion-create")).toContainText("NOT READY");
});

test("settings lists every integration from the server, tests the database live and never fakes a configured key", async ({ page }) => {
  await register(page);
  await page.goto("/app/settings");
  await expect(page.getByTestId("int-database")).toHaveAttribute("data-status", "ready");
  await expect(page.getByTestId("int-database-facts")).toContainText("latency");
  // Nothing is configured on the test server: each of these says so and names the variables to set, with no field to type a secret.
  await expect(page.getByTestId("int-ai-status")).toHaveText("OFF · NOTHING IS GENERATED");
  await expect(page.getByTestId("int-ai-needs")).toContainText("AI_API_KEY");
  await expect(page.getByTestId("int-smtp-needs")).toContainText("SMTP_PASSWORD");
  await expect(page.getByTestId("int-sendgrid-status")).toContainText("NOTHING IS SENT");
  await expect(page.getByTestId("int-twilio-status")).toContainText("NOTHING IS SENT");
  // The CI server records sends in-process (OUTREACH_TEST_SINK) and says so; a real server is in dry-run or live.
  await expect(page.getByTestId("int-sending_mode-status")).toContainText(/DRY-RUN|TEST SINK/);
  await expect(page.locator("input")).toHaveCount(0);

  // A live test of the database: real round trip, measured.
  await page.getByTestId("int-database-test").click();
  await expect(page.getByTestId("int-database-status")).toContainText("VERIFIED");
  await expect(page.getByTestId("int-database-result")).toContainText("A query ran against the database.");

  // A service that is not configured is skipped with the reason, and keeps its real status.
  await page.getByTestId("int-smtp-test").click();
  await expect(page.getByTestId("int-smtp-result")).toContainText("are not all set");
  await expect(page.getByTestId("int-smtp")).toHaveAttribute("data-status", "missing");

  // The town search is called from the browser, so it is tested from the browser (stubbed here: no real network in tests).
  await page.route("https://geo.api.gouv.fr/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ nom: "Lyon" }]) }),
  );
  await page.getByTestId("int-geocoder-test").click();
  await expect(page.getByTestId("int-geocoder-status")).toContainText("VERIFIED");
});

test("one click on a map point adds the business to the CRM, with the attestation and exactly what the map published", async ({ page }) => {
  await register(page);
  await page.route("**/api/prospects/settings", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, flags: { ...real.flags, external_sources: true, prospect_import: true } } });
  });
  await page.route(/(tile\.openstreetmap\.org)/, (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64") }));
  let mine = [];
  await page.route("**/api/map/prospects", (route) => route.fulfill({ json: mine }));
  await page.route(/\/api\/map\/search(\?.*)?$/, (route) =>
    route.fulfill(route.request().method() === "POST" ? { status: 202, json: JOB("succeeded", { id: "j9", result_count: 1 }) } : { json: [] }));
  await page.route("**/api/map/search/j9/places", (route) => route.fulfill({ json: ONE_PLACE }));
  let sent = null;
  await page.route("**/api/map/places/add", async (route) => {
    sent = route.request().postDataJSON();
    mine = [{ id: "p77", name: "Boulangerie Sept", city: "Lyon", lat: 45.76, lon: 4.835, review_status: "approved", has_email: false, external_id: "node/7" }];
    await route.fulfill({
      json: { lead_id: "p77", name: "Boulangerie Sept", created: true, review_status: "approved", in_crm: true, email: null, phone: null, website: null, email_found_on_site: false, website_checked: false, heat: null },
    });
  });
  await page.goto("/app/map");
  await page.getByTestId("map-search").click();
  await expect(page.getByTestId("place-row")).toContainText("Boulangerie Sept");

  await page.locator(".map-pin").first().dispatchEvent("click"); // the pin opens its popup
  const popup = page.getByTestId("place-popup");
  await expect(popup).toContainText("Boulangerie Sept");
  await expect(popup).toContainText("not published"); // the phone and the e-mail were not published: nothing is invented
  await expect(page.getByTestId("place-add")).toBeDisabled(); // no attestation yet
  await page.getByTestId("place-attest").check();
  await page.getByTestId("place-add").click();

  await expect(page.getByTestId("place-added")).toContainText("Boulangerie Sept is added.");
  await expect(page.getByTestId("place-added")).toContainText("in your CRM");
  await expect(page.getByTestId("place-added")).toContainText("Nothing was sent");
  await expect(page.getByTestId("place-open-crm")).toHaveAttribute("href", "/app/leads");
  expect(sent).toMatchObject({ attestation: true, approve: true, check_website: false });
  expect(sent.place).toMatchObject({ external_id: "node/7", name: "Boulangerie Sept", lat: 45.76, lon: 4.835, source_url: "https://www.openstreetmap.org/node/7" });
  expect(sent.place.phone).toBeUndefined();
  // The pin is now one of my prospects (a square) and is no longer offered as a search result.
  await expect(page.getByTestId("map-mine-toggle")).toContainText("1 prospect on the map: 0 to review, 1 approved");
});

async function apiGet(page, path) {
  const token = await page.evaluate(() => localStorage.getItem("outreachos_token"));
  const res = await page.request.get(`${API}/api${path}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(res.status(), await res.text()).toBeLessThan(300);
  return res.json();
}

test("the town search opens on every focus, answers as you type, and shows my counted hot leads in each town", async ({ page }) => {
  await register(page);
  await apiPost(page, "/prospects/discovery/run", { source: "fixture_directory" });
  const towns = await apiGet(page, "/map/cities"); // counted by the server from the real leads of this organisation
  expect(towns.length).toBeGreaterThan(0);
  const top = towns[0];
  const leads = (n) => `${n} lead${n === 1 ? "" : "s"}`;

  await MAP_STUBS(page); // tiles, flags and an empty prospects list: only the town services are faked (the sandbox has no outside access)
  const asked = [];
  await page.route("https://geo.api.gouv.fr/**", (route) => {
    asked.push(decodeURIComponent(route.request().url()));
    return route.fulfill({ json: [{ nom: top.city, code: "00000", codesPostaux: ["00000"], centre: { type: "Point", coordinates: [4.83, 45.76] }, population: 50000, departement: { code: "00", nom: "Test" } }] });
  });
  await page.goto("/app/map");

  // before anything is typed: the towns where my hot leads are, hottest first, with the server's counts
  const field = page.getByTestId("map-goto");
  await field.click();
  await expect(page.getByTestId("city-header")).toHaveText("Your hottest towns");
  await expect(page.getByTestId("map-city-0")).toContainText(top.city);
  await expect(page.getByTestId("map-city-0").getByTestId("city-counts")).toContainText(`${top.hot} hot · ${leads(top.total)}`);
  expect(asked).toHaveLength(0); // nothing leaves the browser until the person types

  // typing: the official list answers, the figures are the same
  await field.fill(top.city.slice(0, 3));
  await expect(page.getByTestId("map-city-0")).toContainText("(00000)");
  await expect(page.getByTestId("map-city-0").getByTestId("city-counts")).toContainText(`${top.hot} hot · ${leads(top.total)}`);
  expect(asked[0]).toContain(`nom=${top.city.slice(0, 3)}`);

  // choosing closes the list; the same field opens it again (the old search showed it once)
  await page.getByTestId("map-city-0").click();
  await expect(page.getByTestId("map-cities")).toHaveCount(0);
  await expect(field).toHaveValue(`${top.city} (00000)`);
  await field.click();
  await expect(page.getByTestId("map-cities")).toBeVisible();
  await field.fill(top.city.slice(0, 2));
  await expect(page.getByTestId("map-city-0")).toContainText(top.city);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("map-cities")).toHaveCount(0);
  await field.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("map-cities")).toBeVisible();
});

test("the TOP leads are marked and have their own lane; empty leads are hidden, counted, and one click brings them back", async ({ page }) => {
  await register(page);
  const heat = (value, over = {}) => ({ value, tier: value >= 65 ? "hot" : value >= 40 ? "warm" : "cold", info_pct: 75, known: ["email", "phone", "website", "city"], missing: ["company"], scored: true, score: value, top: value >= 80, has_contact: true, ...over });
  const lead = (id, name, h, over = {}) => ({ id, org_id: "o", full_name: name, email: `${id}@x.example`, phone: null, company: "Co", title: null, country: "FR", language: "fr", stage: "new", tags: [], source: null, notes: null, score: h.score, email_consent: "unknown", whatsapp_consent: "unknown", created_at: "2026-10-24T10:00:00Z", city: "Lyon", website: null, vertical: null, heat: h, review_status: null, ...over });
  await page.route(/\/api\/leads(\?.*)?$/, (route) =>
    route.fulfill({
      json: [
        lead("t1", "Top Boulangerie", heat(95)),
        lead("t2", "Hot Pizzeria", heat(70)),
        lead("e1", "Nothing Known", heat(0, { has_contact: false, known: [], scored: false, score: null, info_pct: 0 }), { email: null, company: null, country: null, score: 0 }),
        lead("e2", "Only A City", heat(13, { has_contact: false, known: ["city"], scored: false, score: null }), { email: null, score: 0 }),
      ],
    }));
  await page.goto("/app/leads");
  const rows = page.locator('[data-testid^="lead-row-"]');
  await expect(rows).toHaveCount(2); // the two empty leads are not listed
  await expect(page.getByTestId("lane-all")).toHaveText("All 2");
  await expect(page.getByTestId("lane-top")).toHaveText("TOP 1");
  await expect(page.getByTestId("lane-hot")).toHaveText("Hot 2"); // a TOP lead is also hot: the lanes overlap on purpose
  await expect(rows.first().getByTestId("heat-top")).toHaveText("TOP");
  await expect(rows.first().getByTestId("heat-badge")).toHaveAttribute("title", /TOP lead \(heat 80 or more\)/);
  await expect(rows.last().getByTestId("heat-top")).toHaveCount(0);
  await expect(page.getByTestId("leads-empty-toggle-note")).toHaveText("2 empty leads hidden (no e-mail, phone or website).");

  await page.getByTestId("lane-top").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Top Boulangerie");
  await page.getByTestId("lane-all").click();

  await page.getByTestId("leads-empty-toggle").click(); // show them: they come last, and say they are not scored
  await expect(rows).toHaveCount(4);
  await expect(rows.last()).toContainText("not scored");
  await expect(page.getByTestId("leads-empty-toggle-note")).toHaveText("Showing 2 empty leads (no e-mail, phone or website).");
  await page.reload(); // the choice is remembered in this browser
  await expect(rows).toHaveCount(4);
  await page.getByTestId("leads-empty-toggle").click();
  await expect(rows).toHaveCount(2);
});


test("a one-off e-mail is linked to a lead: an unknown address is explained, a lead's address goes through with its lead_id", async ({ page }) => {
  await register(page);
  await apiPost(page, "/leads", { full_name: "Chez Marcel", company: "Marcel SARL", email: "contact@chez-marcel.example" });
  await page.goto("/app/messages");
  await page.getByTestId("new-email-button").click();

  // not a lead: said plainly, with the way out, and nothing can be dispatched
  await page.getByTestId("compose-to").fill("stranger@elsewhere.example");
  await page.getByTestId("compose-body").fill("Hello");
  await expect(page.getByTestId("compose-no-lead")).toContainText("not one of your leads");
  await expect(page.getByTestId("compose-no-lead").getByRole("link")).toHaveAttribute("href", "/app/leads");
  await expect(page.getByTestId("send-message-button")).toBeDisabled();

  // typing a name offers the lead; picking it fills its address and links it
  await page.getByTestId("compose-to").fill("marcel");
  await page.getByTestId("compose-suggest-0").click();
  await expect(page.getByTestId("compose-to")).toHaveValue("contact@chez-marcel.example");
  await expect(page.getByTestId("compose-lead")).toContainText("Linked to Chez Marcel");
  await page.getByTestId("compose-subject").fill("Bonjour");
  let sent = null;
  await page.route("**/api/messages/email", (route) => { sent = route.request().postDataJSON(); return route.continue(); });
  await expect(page.getByTestId("send-message-button")).toBeEnabled();
  await page.getByTestId("send-message-button").click();
  await expect(page.getByTestId("new-email-button")).toBeVisible();
  await expect(page.locator("table tbody tr").first()).toContainText("contact@chez-marcel.example");
  expect(sent).toMatchObject({ to: "contact@chez-marcel.example", subject: "Bonjour" });
  expect(sent.lead_id).toMatch(/^[0-9a-f-]{36}$/); // the footer's unsubscribe link belongs to this lead
});
