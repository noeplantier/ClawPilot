// Settings must show what the server really has configured: no hard-coded "ACTIVE".
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { full_name: "Ada", email: "a@x.example", role: "owner" }, org: { id: "o1", name: "Org", plan: "pro" } }),
}));

import { api } from "@/lib/api";
import Settings from "@/pages/Settings";

global.IS_REACT_ACT_ENVIRONMENT = true;

const BASE = {
  sendgrid_from_email: null,
  twilio_whatsapp_from: null,
  twilio_account_sid_configured: false,
  sendgrid_configured: false,
  ai: { key_configured: false, library_available: false, active: false, mode: "template", reason: "EMERGENT_LLM_KEY is not set" },
  outreach: {
    dry_run: true, live_sending_flag: false, kill_switch: false, sender_configured: false, sender_email: null,
    smtp_configured: false, smtp_host: null, sandbox: true, allowlist_size: 0,
  },
  webhooks: { production: false, twilio_signature_ready: false, twilio_webhook_url_set: false, sendgrid_signature_ready: false },
};

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function show(data) {
  api.get.mockResolvedValue({ data });
  await act(async () => root.render(<Settings />));
  await act(async () => {});
}
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const merge = (patch) => ({ ...BASE, ...patch });

describe("Settings integrations", () => {
  it("does not claim the AI is active when no model can be called, and says why", async () => {
    await show(BASE);
    expect(byId("row-ai-status").textContent).toContain("TEMPLATE ONLY");
    expect(byId("row-ai").textContent).toContain("EMERGENT_LLM_KEY is not set");
    expect(container.textContent).not.toContain("MODEL CALLED");
  });

  it("shows the AI as live only when the server reports it", async () => {
    await show(merge({ ai: { key_configured: true, library_available: true, active: true, mode: "live", reason: null } }));
    expect(byId("row-ai-status").textContent).toContain("LIVE");
    expect(byId("row-ai").textContent).toContain("installed");
  });

  it("reports a missing package even when the key is set", async () => {
    await show(merge({ ai: { key_configured: true, library_available: false, active: false, mode: "template", reason: "the emergentintegrations package is not installed" } }));
    expect(byId("row-ai-status").textContent).toContain("TEMPLATE ONLY");
    expect(byId("row-ai").textContent).toContain("not installed");
  });

  it("reflects each provider's configuration and lists what is missing", async () => {
    await show(merge({ sendgrid_configured: true, sendgrid_from_email: "founder@plantiers.com" }));
    expect(byId("row-sendgrid-status").textContent).toContain("CONFIGURED");
    expect(byId("row-sendgrid").textContent).toContain("founder@plantiers.com");
    expect(byId("row-twilio-status").textContent).toContain("NOT CONFIGURED");
    const missing = byId("missing-config").textContent;
    expect(missing).toContain("TWILIO_ACCOUNT_SID");
    expect(missing).not.toContain("SENDGRID_API_KEY");
  });

  it("shows dry-run, live and kill-switch states distinctly", async () => {
    await show(BASE);
    expect(byId("row-outreach-status").textContent).toContain("DRY-RUN");
    await act(async () => root.unmount());
    root = createRoot(container);
    const live = { ...BASE.outreach, dry_run: false, live_sending_flag: true, sender_configured: true, sender_email: "founder@plantiers.com" };
    await show(merge({ outreach: live }));
    expect(byId("row-outreach-status").textContent).toContain("SMTP INCOMPLETE");
    await act(async () => root.unmount());
    root = createRoot(container);
    await show(merge({ outreach: { ...live, smtp_configured: true, smtp_host: "smtp.example", sandbox: true, allowlist_size: 1 } }));
    expect(byId("row-outreach-status").textContent).toContain("SANDBOX");
    expect(byId("row-outreach").textContent).toContain("smtp.example");
    expect(byId("row-outreach").textContent).toContain("on (1 allowed)");
    await act(async () => root.unmount());
    root = createRoot(container);
    await show(merge({ outreach: { ...live, smtp_configured: true, smtp_host: "smtp.example", sandbox: false } }));
    expect(byId("row-outreach-status").textContent).toContain("REAL E-MAIL");
    await act(async () => root.unmount());
    root = createRoot(container);
    await show(merge({ outreach: { ...BASE.outreach, kill_switch: true } }));
    expect(byId("row-outreach-status").textContent).toContain("KILL SWITCH");
  });

  it("has no warning banner when everything is configured", async () => {
    await show({
      sendgrid_from_email: "a@b.example", twilio_whatsapp_from: "whatsapp:+1", twilio_account_sid_configured: true, sendgrid_configured: true,
      ai: { ...BASE.ai, key_configured: true, library_available: true, active: true, mode: "live", reason: null },
      outreach: { ...BASE.outreach, sender_configured: true, sender_email: "a@b.example", smtp_configured: true, smtp_host: "smtp.example" },
      webhooks: { production: true, twilio_signature_ready: true, twilio_webhook_url_set: true, sendgrid_signature_ready: true },
    });
    expect(byId("missing-config")).toBeNull();
    expect(byId("row-webhooks-status").textContent).toContain("BOTH VERIFIED");
  });

  it("shows an error with retry instead of default 'ACTIVE' labels when the server cannot be read", async () => {
    api.get.mockRejectedValue({ response: { status: 500, data: { detail: "boom" } } });
    await act(async () => root.render(<Settings />));
    await act(async () => {});
    expect(container.querySelector('[data-testid="error-block"]').textContent).toContain("boom");
    expect(container.textContent).not.toContain("ACTIVE");
    expect(byId("row-ai")).toBeNull();
  });
});
