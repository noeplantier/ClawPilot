// « Fournisseur d'envoi », sans réseau : le fournisseur actuel vient de l'API, un relais choisi donne ses réglages publics,
// jamais un mot de passe.
import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { api } from "@/lib/api";
import { clear } from "@/lib/swr";
import ProviderSwitch from "@/components/outreach/ProviderSwitch";

global.IS_REACT_ACT_ENVIRONMENT = true;

const DATA = {
  current: { id: "smtp_hostinger", label: "SMTP Hostinger (smtp.hostinger.com)", host: "smtp.hostinger.com", restriction: "Messagerie mutualisée Hostinger…", shared_mailbox: true, is_relay: false },
  replies_read: true,
  relays: [
    { id: "brevo", name: "Brevo", host: "smtp-relay.brevo.com", port: 587, security: "starttls", username_hint: "l'identifiant SMTP", note: "UE.", recommended: true, active: false },
    { id: "mailjet", name: "Mailjet", host: "in-v3.mailjet.com", port: 587, security: "starttls", username_hint: "la clé API", note: "UE.", recommended: false, active: false },
  ],
  server_variables: ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"],
};

let container;
let root;
beforeEach(() => {
  clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  api.get.mockResolvedValue({ data: DATA });
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

test("says that a shared mailbox limits campaigns, and offers the recommended relay first", async () => {
  await act(async () => { root.render(<ProviderSwitch />); });
  await act(async () => {});
  expect(byId("provider-current").textContent).toContain("Hostinger");
  expect(byId("provider-verdict").textContent).toMatch(/opt-in/);
  expect(byId("relay-lines").textContent).toContain("SMTP_HOST=smtp-relay.brevo.com");
  await act(async () => { byId("relay-mailjet").click(); });
  expect(byId("relay-lines").textContent).toContain("SMTP_HOST=in-v3.mailjet.com");
  expect(byId("relay-lines").textContent).toContain("SMTP_PASSWORD=<à saisir sur le serveur>"); // named, never filled in
});

const RESEND = {
  ...DATA,
  current: { id: "resend_api", label: "Resend (API HTTPS)", host: "api.resend.com", restriction: "Resend : service d'envoi par API…", shared_mailbox: false, is_relay: false, is_api: true },
  api_channels: [
    { id: "resend", name: "Resend", variable: "RESEND_API_KEY", configured: true, active: true, recommended: true, note: "API HTTPS, essayé en premier." },
    { id: "brevo", name: "Brevo", variable: "BREVO_API_KEY", configured: false, active: false, recommended: false, note: "API HTTPS, essayé après Resend." },
  ],
  server_variables: ["RESEND_API_KEY", "BREVO_API_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME", "SMTP_PASSWORD"],
};

test("with Resend in use: says it sends, and folds the SMTP relays that would change nothing", async () => {
  api.get.mockResolvedValue({ data: RESEND });
  await act(async () => { root.render(<ProviderSwitch />); });
  await act(async () => {});
  expect(byId("provider-verdict").textContent).toMatch(/Service d'envoi par API/);
  expect(byId("provider-verdict").textContent).not.toMatch(/inconnu/);
  expect(byId("api-order").textContent).toContain("Resend est le premier configuré, c'est lui qui envoie");
  expect(byId("api-resend-state").textContent).toBe("utilisé");
  expect(byId("api-brevo-state").textContent).toBe("non configuré");
  expect(byId("api-brevo").textContent).toContain("BREVO_API_KEY=<à saisir sur le serveur>"); // named, never filled in
  expect(byId("smtp-relays").tagName).toBe("DETAILS");
  expect(byId("smtp-relays").open).toBe(false);
  expect(byId("smtp-relays").textContent).toContain("inutilisés tant que Resend est configuré");
  expect(container.textContent).toContain("RESEND_API_KEY, BREVO_API_KEY, SMTP_HOST");
});

test("with nothing configured: the API keys come first, the SMTP relays as the alternative", async () => {
  const none = { ...RESEND, current: { id: "none", label: "Aucun fournisseur configuré", host: null, restriction: "…", shared_mailbox: false, is_relay: false, is_api: false },
    api_channels: RESEND.api_channels.map((c) => ({ ...c, configured: false, active: false })) };
  api.get.mockResolvedValue({ data: none });
  await act(async () => { root.render(<ProviderSwitch />); });
  await act(async () => {});
  expect(byId("provider-verdict").textContent).toMatch(/Aucun fournisseur/);
  expect(container.textContent).toContain("Le plus simple : une clé d'API");
  expect(byId("api-order").textContent).toContain("port 443");
  expect(byId("smtp-relays").tagName).toBe("DIV");
  expect(byId("smtp-relays").textContent).toContain("Ou un relais d'envoi B2B (SMTP)");
});
