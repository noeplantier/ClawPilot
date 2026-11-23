// Formatage pur du parcours « zone → brouillon → approbation » : aucun appel réseau, aucune donnée inventée.
// Tout chiffre vient de la réponse du serveur ; « livré » n'existe pas (un serveur SMTP qui accepte n'est pas une preuve).
import { formatDateTime } from "@/lib/outreachFormat";

// La zone portée par l'adresse (`/app/journey?south=…&category=…`) : valide, ordonnée, ou rien. Le serveur revalide de toute façon.
export function zoneFromSearch(search) {
  const q = new URLSearchParams(search || "");
  const [south, west, north, east] = ["south", "west", "north", "east"].map((k) => Number(q.get(k)));
  const category = (q.get("category") || "").trim();
  if (![south, west, north, east].every(Number.isFinite) || q.get("south") === "" || !category) return null;
  if (!(south < north && west < east && south >= -90 && north <= 90 && west >= -180 && east <= 180)) return null;
  const label = (q.get("label") || "").trim();
  return { south, west, north, east, category, ...(label ? { label } : {}) };
}

// L'onboarding en une fois : ce qui bloque (avec la correction exacte) d'abord, puis ce qui informe sans bloquer.
export function readinessView(readiness) {
  const items = (readiness && readiness.items) || [];
  return {
    ready: Boolean(readiness && readiness.ready),
    blockers: items.filter((i) => i.blocking && !i.ok),
    warnings: items.filter((i) => !i.blocking && !i.ok),
    notes: items.filter((i) => i.ok && i.note),
    done: items.filter((i) => i.ok).length,
    total: items.length,
  };
}

// Où en est l'approbation : jamais « approuvée » si elle ne couvre plus ce qui est affiché.
export function approvalState(approval) {
  if (!approval || !approval.approved) return { key: "none", label: "Pas encore approuvée", tone: "chip-ink" };
  if (approval.revoked_at) return { key: "revoked", label: "Approbation retirée : rien ne partira sans nouvelle approbation", tone: "chip-danger" };
  if (!approval.valid) {
    const why = (approval.reasons || []).map((r) => r.label).join(" ");
    return { key: "stale", label: why || "L'approbation ne couvre plus ce qui est affiché : approuvez à nouveau.", tone: "chip-warn" };
  }
  return { key: "valid", label: `Approuvée pour la version ${approval.template_version} du message`, tone: "chip-success" };
}

// Pourquoi le bouton « Approuver » est (encore) fermé, en une phrase ; null = on peut approuver.
export function approveBlock(summary, decide = true) {
  if (!summary) return "Chargement…";
  if (!decide) return "Seuls un propriétaire ou un administrateur peuvent approuver.";
  if (!summary.readiness.ready) return "Terminez d'abord la configuration ci-dessus : chaque point bloquant dit quoi faire.";
  if ((summary.template.problems || []).length > 0) return "Corrigez le message : un point manque ou n'est pas permis.";
  if (summary.audience.sendable === 0) return summary.audience.held_back_count > 0 ? "Aucun message ne peut partir : voir les établissements retenus." : "Aucun établissement de cette zone ne peut recevoir ce message.";
  if (approvalState(summary.approval).key === "valid") return "Cette version est déjà approuvée.";
  return null;
}

export const volumeLine = (volume) => {
  if (!volume) return "";
  const n = volume.messages;
  return `${n} message${n === 1 ? "" : "s"}, un par destinataire · au plus ${volume.daily_cap} par jour · plafond total ${volume.total_cap}.`;
};

export function scheduleLine(schedule) {
  if (!schedule || !schedule.first_at) return "Aucun envoi à planifier.";
  const days = (schedule.days || []).length;
  return `Du ${formatDateTime(schedule.first_at)} au ${formatDateTime(schedule.last_at)} (${schedule.timezone}), sur ${days} jour${days === 1 ? "" : "s"} : le serveur revérifie chaque envoi au moment où il part.`;
}

export function exclusionRows(audience) {
  const counts = (audience && audience.exclusions) || {};
  const labels = (audience && audience.exclusion_labels) || {};
  return Object.entries(counts).filter(([, n]) => n > 0).map(([code, n]) => ({ code, count: n, label: labels[code] || code })).sort((a, b) => b.count - a.count);
}

// Les états du suivi, dans les mots de ce que le système sait vraiment.
export const TRACK_LABEL = {
  scheduled: "Planifiés",
  sending: "En cours d'envoi",
  simulated: "Simulés (rien n'est parti)",
  accepted: "Acceptés par le serveur SMTP",
  replied: "Réponses",
  opted_out: "Oppositions",
  bounced: "Rebonds",
  failed: "Refusés",
  unknown: "Résultat inconnu",
  skipped: "Écartés au moment de l'envoi",
  cancelled: "Annulés",
};

export function trackingRows(states) {
  return Object.entries(states || {}).filter(([, n]) => n > 0).map(([key, n]) => ({ key, count: n, label: TRACK_LABEL[key] || key }));
}

export function progressLine(progress) {
  if (!progress || !progress.total) return "Rien n'est planifié pour l'instant.";
  return `${progress.done} sur ${progress.total} traités${progress.percent === null || progress.percent === undefined ? "" : ` (${progress.percent} %)`}.`;
}

// Insère un champ de fusion à la position du curseur ; renvoie le texte et la nouvelle position du curseur.
export function insertToken(text, start, end, token) {
  const a = Math.max(0, Math.min(start ?? text.length, text.length));
  const b = Math.max(a, Math.min(end ?? a, text.length));
  return { text: text.slice(0, a) + token + text.slice(b), caret: a + token.length };
}

export const journeyStatus = (status) => ({ draft: "En préparation", running: "En cours", paused: "En pause", completed: "Terminée" }[status] || status);
