// Pure formatting of the autopilot (GET /autopilot). Every value comes from the server; nothing is guessed.
export const ACK_LABELS = {
  b2b_use: "J'ai le droit d'utiliser les coordonnées professionnelles publiées sur la carte pour de la prospection B2B, et je respecte les désinscriptions.",
  auto_approve: "Les prospects que le serveur qualifie sont approuvés en mon nom ; chaque décision est écrite dans le journal.",
  ai_credits: "Préparer les brouillons consomme des crédits d'IA, dans les limites de session et de jour.",
  can_stop: "Je peux l'arrêter à tout instant ; il n'envoie jamais rien lui-même (le mandat envoie, dans ses plafonds).",
};

// What the full automatic chain still needs on the server, as named switches (never a value).
export function missingRequirements(req) {
  if (!req) return [];
  const out = [];
  if (!req.external_sources) out.push({ key: "external_sources", label: "Recherche automatique sur la carte", fix: "FEATURE_EXTERNAL_SOURCES=true" });
  if (!req.prospect_import) out.push({ key: "prospect_import", label: "Ajout des établissements trouvés", fix: "FEATURE_PROSPECT_IMPORT=true" });
  if (!req.automation_max) out.push({ key: "automation_max", label: "Envoi par le mandat", fix: "FEATURE_AUTOMATION_MAX=true" });
  if (!req.live_sending) out.push({ key: "live_sending", label: "Envoi réel (sinon simulation)", fix: "FEATURE_LIVE_SENDING=true" });
  return out;
}

// One line for the last run, from the server's own counts.
export function runSummary(run) {
  if (!run) return "";
  const parts = [];
  const d = run.discovery;
  if (d && d.search === "ok") parts.push(`${d.found} lieu(x) trouvé(s), ${d.reachable} joignable(s), ${d.created || 0} ajouté(s)`);
  else if (d && d.search === "skipped") parts.push(`Recherche non lancée : ${d.why}`);
  else if (d && d.search === "failed") parts.push(`Recherche échouée (${d.why})`);
  if (run.approval) parts.push(`${run.approval.approved || 0} prospect(s) approuvé(s)`);
  if (run.drafts) parts.push(`${run.drafts.ready || 0} brouillon(s) prêt(s)`);
  return parts.length ? `${parts.join(" · ")}. Rien n'a été envoyé par le pilote.` : "Rien à faire pour l'instant.";
}

export const frequencyLabel = (h) => (h % 24 === 0 && h > 24 ? `tous les ${h / 24} jours` : `toutes les ${h} h`);
