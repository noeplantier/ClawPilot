// Pure: the lines an operator sets on the server to move to a relay. Public settings only; the login and the password are
// named, never filled in (they are typed on the host, never in the application).
export function serverLines(relay) {
  if (!relay) return [];
  return [
    `SMTP_HOST=${relay.host}`,
    `SMTP_PORT=${relay.port}`,
    `SMTP_SECURITY=${relay.security}`,
    "SMTP_USERNAME=<à saisir sur le serveur>",
    "SMTP_PASSWORD=<à saisir sur le serveur>",
  ];
}

// What the provider in use means for a campaign, in one line.
export function providerVerdict(current) {
  if (!current || current.id === "none") return { tone: "danger", label: "Aucun fournisseur : rien ne peut partir pour de vrai." };
  if (current.shared_mailbox) return { tone: "warn", label: "Messagerie mutualisée : campagnes réservées aux contacts avec opt-in." };
  if (current.is_relay) return { tone: "success", label: "Relais d'envoi dédié : conditions à vérifier par vous, puis envoi possible." };
  return { tone: "ink", label: "Fournisseur inconnu de l'application : vérifiez ses conditions." };
}
