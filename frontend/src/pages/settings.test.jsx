// Settings must show what the server really has configured, entry by entry: no hard-coded "ACTIVE", no secret, no invented status.
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
let mockRole = "owner";
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { full_name: "Ada", email: "a@x.example", role: mockRole }, org: { id: "o1", name: "Org", plan: "pro" } }),
}));

import { api } from "@/lib/api";
import Settings from "@/pages/Settings";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mk = (id, group, status, label, extra = {}) => ({
  id, name: `name-${id}`, group, status, label, summary: `summary of ${id}`, env: [], needs: [], facts: [], test: null, hint: null,
  docs: `docs/integrations.md#${id}`, ...extra,
});

// What a bare server (nothing configured) returns, in the shape of GET /settings/integrations.
const BARE = {
  items: [
    mk("database", "data", "ready", "CONNECTED", { test: "server", facts: [["host.kind", "Supabase · Session pooler"], ["latency", "12 ms"]] }),
    mk("osm", "sources", "unchecked", "KEYLESS · NOT TESTED", { test: "server" }),
    mk("geocoder", "sources", "unchecked", "KEYLESS · NOT TESTED", { test: "browser" }),
    mk("smtp", "sending", "missing", "NOT CONFIGURED", { test: "server", needs: ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"], env: ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"] }),
    mk("sendgrid", "sending", "unchecked", "CONFIGURED · NOT TESTED", { test: "server", hint: "The test only reads the key's scopes." }),
    mk("twilio_webhook", "inbound", "off", "NOT NEEDED YET"),
    mk("ai", "ai", "missing", "OFF · NOTHING IS GENERATED", { test: "server", needs: ["AI_PROVIDER", "AI_API_KEY"], summary: "Nothing is generated and no canned text is offered until it is configured. Reason: AI_PROVIDER is not set (groq, gemini, mistral or custom)." }),
  ],
  counts: {},
};

let container;
let root;
beforeEach(() => {
  mockRole = "owner";
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  api.post.mockReset();
  global.fetch = jest.fn();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function show(data = BARE) {
  api.get.mockResolvedValue({ data });
  await act(async () => root.render(<Settings />));
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const click = async (id) => { await act(async () => { byId(id).click(); }); await act(async () => {}); };

describe("Settings integrations", () => {
  it("renders one card per integration the server returns, with the server's own label", async () => {
    await show();
    for (const item of BARE.items) {
      expect(byId(`int-${item.id}`)).not.toBeNull();
      expect(byId(`int-${item.id}-status`).textContent).toContain(item.label);
    }
    expect(byId("group-data")).not.toBeNull();
    expect(byId("group-inbound")).not.toBeNull();
  });

  it("does not claim the AI is active when no model can be called, and says why and what to set", async () => {
    await show();
    expect(byId("int-ai-status").textContent).toContain("NOTHING IS GENERATED");
    expect(byId("int-ai").textContent).toContain("AI_PROVIDER is not set");
    expect(byId("int-ai-needs").textContent).toContain("AI_PROVIDER");
    expect(byId("int-ai-needs").textContent).toContain("AI_API_KEY");
    expect(container.textContent).not.toContain("MODEL CALLED");
  });

  it("counts from the entries: a configured but untested service is never counted as ready", async () => {
    await show();
    expect(byId("sum-ready").textContent).toBe("1 READY");
    expect(byId("sum-unchecked").textContent).toBe("3 NOT TESTED");
    expect(byId("sum-attention").textContent).toBe("2 NEED ATTENTION");
    expect(byId("sum-off").textContent).toBe("1 OFF");
  });

  it("lists the exact variable names to set and never offers a field to type a secret", async () => {
    await show();
    const needs = byId("int-smtp-needs").textContent;
    for (const name of ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]) expect(needs).toContain(name);
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    expect(byId("int-secrets-note").textContent).toContain("never typed or shown here");
    expect(byId("int-sendgrid-hint").textContent).toContain("scopes");
  });

  it("a passed server test marks the entry verified, with the measured latency", async () => {
    await show();
    api.post.mockResolvedValue({ data: { id: "sendgrid", ok: true, outcome: "passed", latency_ms: 87, detail: "SendGrid accepted the key.", checked_at: "2026-10-23T10:00:00Z" } });
    await click("int-sendgrid-test");
    expect(api.post).toHaveBeenCalledWith("/settings/integrations/sendgrid/test");
    expect(byId("int-sendgrid-status").textContent).toBe("VERIFIED · 87 ms");
    expect(byId("int-sendgrid-result").textContent).toContain("SendGrid accepted the key.");
    expect(byId("sum-ready").textContent).toBe("2 READY");
  });

  it("a failed test turns the entry red with the reason; a service with a fallback only turns amber", async () => {
    await show();
    api.post.mockResolvedValueOnce({ data: { ok: false, outcome: "failed", latency_ms: 20, detail: "SendGrid rejected the key (HTTP 401).", checked_at: "x" } });
    await click("int-sendgrid-test");
    expect(byId("int-sendgrid").dataset.status).toBe("blocked");
    expect(byId("int-sendgrid-result").textContent).toContain("rejected the key");
    api.post.mockResolvedValueOnce({ data: { ok: false, outcome: "failed", latency_ms: 20, detail: "No OpenStreetMap server answered.", checked_at: "x" } });
    await click("int-osm-test");
    expect(byId("int-osm").dataset.status).toBe("partial");
  });

  it("a skipped test or an API error keeps the server's status instead of inventing one", async () => {
    await show();
    api.post.mockResolvedValueOnce({ data: { ok: false, outcome: "skipped", latency_ms: null, detail: "SMTP_HOST … are not all set.", checked_at: "x" } });
    await click("int-smtp-test");
    expect(byId("int-smtp").dataset.status).toBe("missing");
    api.post.mockRejectedValueOnce({ response: { status: 429, data: { detail: "Test limit reached: wait a minute" } } });
    await click("int-sendgrid-test");
    expect(byId("int-sendgrid").dataset.status).toBe("unchecked");
    expect(byId("int-sendgrid-result").textContent).toContain("Test limit reached");
  });

  it("tests the city search from the browser, not through the API", async () => {
    await show();
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [{ nom: "Lyon" }] });
    await click("int-geocoder-test");
    expect(api.post).not.toHaveBeenCalled();
    expect(global.fetch.mock.calls[0][0]).toContain("geo.api.gouv.fr/communes");
    expect(byId("int-geocoder-status").textContent).toContain("VERIFIED");
  });

  it("only an owner or an admin can run the server checks; the browser check stays open", async () => {
    mockRole = "member";
    await show();
    expect(byId("int-sendgrid-test").disabled).toBe(true);
    expect(byId("int-geocoder-test").disabled).toBe(false);
  });

  it("run checks only tests what is configured and spares the rate limit", async () => {
    await show();
    api.post.mockImplementation((url) => Promise.resolve({ data: { ok: true, outcome: "passed", latency_ms: 5, detail: `ok ${url}`, checked_at: "x" } }));
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ features: [{}] }) });
    await click("int-run-all");
    const called = api.post.mock.calls.map(([url]) => url).sort();
    expect(called).toEqual(["/settings/integrations/database/test", "/settings/integrations/osm/test", "/settings/integrations/sendgrid/test"]);
    expect(called.join()).not.toContain("smtp"); // not configured: nothing to test
    expect(byId("int-geocoder-status").textContent).toContain("VERIFIED");
  });

  it("shows an error with retry instead of default 'ACTIVE' labels when the server cannot be read", async () => {
    api.get.mockRejectedValue({ response: { status: 500, data: { detail: "boom" } } });
    await act(async () => root.render(<Settings />));
    await act(async () => {});
    expect(container.querySelector('[data-testid="error-block"]').textContent).toContain("boom");
    expect(container.textContent).not.toContain("ACTIVE");
    expect(byId("int-ai")).toBeNull();
  });

  it("re-reads the server on its own and says when a refresh failed", async () => {
    jest.useFakeTimers();
    try {
      await show();
      expect(api.get).toHaveBeenCalledTimes(1);
      const next = { ...BARE, items: BARE.items.map((i) => (i.id === "smtp" ? { ...i, status: "unchecked", label: "CONFIGURED · NOT TESTED", needs: [] } : i)) };
      api.get.mockResolvedValue({ data: next });
      await act(async () => { jest.advanceTimersByTime(30000); });
      expect(api.get).toHaveBeenCalledTimes(2);
      expect(byId("int-smtp-status").textContent).toContain("CONFIGURED");
      expect(byId("int-smtp-needs")).toBeNull();
      api.get.mockRejectedValue(new Error("offline"));
      await act(async () => { jest.advanceTimersByTime(30000); });
      expect(byId("int-live").textContent).toContain("Refresh failed");
      expect(byId("int-smtp-status").textContent).toContain("CONFIGURED"); // the last data stays
    } finally {
      jest.useRealTimers();
    }
  });
});
