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
