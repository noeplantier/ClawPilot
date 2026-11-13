import { providerVerdict, serverLines } from "@/lib/providerFormat";

test("the server lines carry the public settings and never a secret", () => {
  const lines = serverLines({ host: "smtp-relay.brevo.com", port: 587, security: "starttls" });
  expect(lines.slice(0, 3)).toEqual(["SMTP_HOST=smtp-relay.brevo.com", "SMTP_PORT=587", "SMTP_SECURITY=starttls"]);
  expect(lines.filter((l) => l.startsWith("SMTP_PASSWORD"))[0]).toBe("SMTP_PASSWORD=<à saisir sur le serveur>");
  expect(serverLines(null)).toEqual([]);
});

test("a shared mailbox, a relay and nothing say different things", () => {
  expect(providerVerdict({ id: "smtp_hostinger", shared_mailbox: true }).tone).toBe("warn");
  expect(providerVerdict({ id: "smtp_brevo", is_relay: true }).tone).toBe("success");
  expect(providerVerdict({ id: "none" }).tone).toBe("danger");
  expect(providerVerdict({ id: "smtp" }).tone).toBe("ink");
});
