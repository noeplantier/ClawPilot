// Formatage pur de l'écran « Canaux d'envoi » : une décision (« puis-je envoyer maintenant ? »), quelques pastilles d'état et
// une ligne de volumes, tout depuis la réponse de GET /outbound/status. Une valeur absente s'affiche « — », jamais 0.

// Les raisons de blocage du serveur (services/send_gate.py), en mots qu'on peut suivre.
export const BLOCKED_REASON = {
  kill_switch: "arrêt d'urgence activé sur le serveur (SEND_KILL_SWITCH)",
  paused: "envoi en pause pour ce compte",
  daily: "limite du jour atteinte",
  hourly: "limite de l'heure atteinte",
  delay: "délai minimal entre deux messages pas encore écoulé",
};

const count = (n) => (Number.isFinite(n) ? String(n) : "—");

// « réessai à 14:05 (dans 12 min) », ou null sans heure valable.
export function retryText(iso, now = new Date()) {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const minutes = Math.max(0, Math.ceil((at.getTime() - now.getTime()) / 60000));
  const when = at.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (minutes < 1) return `réessai possible maintenant (${when})`;
  return minutes < 120 ? `réessai à ${when} (dans ${minutes} min)` : `réessai à ${when} (dans ${Math.round(minutes / 60)} h)`;
}

export function lastDispatchText(iso) {
  if (!iso) return "aucun pour l'instant";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// { canSend, headline, chips: [{ key, label, tone, testId }], volumes } ; null tant que le statut n'est pas chargé.
export function statusSummary(status, settings, now = new Date()) {
  if (!status) return null;
  const blocked = status.blocked_by;
  const retry = blocked ? retryText(status.next_allowed_at, now) : null;
  const headline = blocked
    ? `Envoi bloqué : ${BLOCKED_REASON[blocked] || blocked}${retry ? ` · ${retry}` : ""}.`
    : status.dry_run
      ? "Envoi possible maintenant, en simulation : rien ne part réellement."
      : "Envoi possible maintenant : les messages partent pour de vrai.";
  const sender = settings ? (settings.sender_configured ? "configurée" : "non configurée") : "—";
  const chips = [
    { key: "mode", testId: "fact-mode", label: status.dry_run ? "Simulation : rien ne part" : "Envoi réel", tone: status.dry_run ? "chip-cold" : "chip-success" },
    { key: "kill", testId: "fact-kill", label: status.kill_switch ? "Arrêt d'urgence : ACTIVÉ" : "Arrêt d'urgence : inactif", tone: status.kill_switch ? "chip-danger" : "chip-ink" },
    { key: "paused", testId: "fact-paused", label: status.paused ? "Compte : en pause" : "Compte : actif", tone: status.paused ? "chip-warn" : "chip-ink" },
    { key: "sender", testId: "fact-sender", label: `Identité d'expéditeur : ${sender}`, tone: settings && !settings.sender_configured ? "chip-danger" : "chip-ink" },
  ];
  const volumes = [
    { key: "today", testId: "fact-today", label: "Aujourd'hui", value: count(status.sent_today) },
    { key: "hour", testId: "fact-hour", label: "Dernière heure", value: count(status.sent_last_hour) },
    { key: "last", testId: "fact-last", label: "Dernier envoi", value: lastDispatchText(status.last_dispatched_at) },
  ];
  return { canSend: !blocked, headline, chips, volumes };
}
