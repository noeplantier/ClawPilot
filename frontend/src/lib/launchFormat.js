// Formatage pur de l'écran « Campagne individuelle » : aucun appel réseau, aucune donnée inventée.
// Tout chiffre vient de la réponse du serveur ; un état inconnu s'affiche comme tel et ne vaut jamais un défaut.

// Les trois états du site web. « Aucun site identifié » n'est affirmé que si l'annuaire a été lu et n'en portait pas ;
// un champ vide seul reste « inconnu ».
export const SITE_STATE_FR = {
  site_found: { label: "Site présent", chip: "chip-success" },
  site_unreachable: { label: "Site présent, injoignable à la dernière vérification", chip: "chip-warn" },
  none_identified: { label: "Aucun site identifié après recherche", chip: "chip-ink" },
  unknown: { label: "Site inconnu (non vérifié)", chip: "chip-cold" },
};

export function siteState(state) {
  return SITE_STATE_FR[state] || SITE_STATE_FR.unknown;
}

// Où en est chaque destinataire, dans l'ordre du parcours.
export const STAGES = [
  { key: "no_draft", label: "Sans brouillon", chip: "chip-warn", hint: "Aucun brouillon : rien n'est inventé à sa place." },
  { key: "to_review", label: "À relire", chip: "chip-warn", hint: "Brouillon prêt, en attente de votre validation." },
  { key: "blocked", label: "Bloqués", chip: "chip-danger", hint: "Brouillon approuvé mais un point bloque l'envoi." },
  { key: "rejected", label: "Rejetés", chip: "chip-ink", hint: "Brouillon rejeté : il ne partira pas." },
  { key: "ready", label: "Prêts", chip: "chip-success", hint: "Approuvés et propres : ils seront planifiés." },
  { key: "planned", label: "Planifiés", chip: "chip-ink", hint: "Un créneau d'envoi est réservé." },
  { key: "launched", label: "Partis", chip: "chip-ink", hint: "Pris en charge par l'envoi : voir le suivi." },
  { key: "excluded", label: "Exclus", chip: "chip-danger", hint: "Ne peuvent plus recevoir cette campagne (raison indiquée)." },
];

export const stageMeta = (key) => STAGES.find((s) => s.key === key) || { key, label: key, chip: "chip-ink", hint: "" };

// Le suivi honnête : jamais « livré » — personne ne l'observe.
export const TRACKING_CHIP = {
  scheduled: "chip-ink",
  sending: "chip-warn",
  simulated: "chip-cold",
  accepted: "chip-success",
  replied: "chip-success",
  opted_out: "chip-danger",
  bounced: "chip-danger",
  failed: "chip-danger",
  unknown: "chip-warn",
  skipped: "chip-warn",
  cancelled: "chip-ink",
};

export const TRACKING_ORDER = ["scheduled", "sending", "accepted", "simulated", "replied", "opted_out", "bounced", "failed", "unknown", "skipped", "cancelled"];

export const DELIVERY_NOTE =
  "« Accepté par SMTP » signifie que le serveur d'envoi a pris le message en charge. Ce n'est pas une preuve de livraison : " +
  "aucun accusé n'est observé, donc aucun message n'est jamais marqué « livré ».";

// [{code, label, count}] du plus fréquent au moins fréquent, à partir des compteurs et des libellés du serveur.
export function exclusionLines(counts, labels) {
  return Object.entries(counts || {})
    .filter(([, n]) => n > 0)
    .map(([code, count]) => ({ code, label: (labels && labels[code]) || code, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "fr"));
}

// Les exclusions d'une création, regroupées par raison (la liste du serveur donne une ligne par prospect écarté).
export function groupExcluded(excluded) {
  const groups = new Map();
  (excluded || []).forEach((item) => {
    const g = groups.get(item.code) || { code: item.code, label: item.label, items: [] };
    g.items.push(item);
    groups.set(item.code, g);
  });
  return [...groups.values()].sort((a, b) => b.items.length - a.items.length);
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many || `${one}s`}`;

function dayFormat(iso, timeZone, options) {
  if (!iso) return null;
  try {
    return new Intl.DateTimeFormat("fr-FR", { timeZone: timeZone || "UTC", ...options }).format(new Date(iso));
  } catch {
    return null;
  }
}

export const formatSlot = (iso, timeZone) =>
  dayFormat(iso, timeZone, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const formatDay = (isoDate, timeZone) => dayFormat(`${isoDate}T12:00:00Z`, timeZone, { weekday: "short", day: "numeric", month: "short" });

// « 100 messages, du ven. 6 nov. 09:00 au mer. 11 nov. 17:12 (fuseau Europe/Paris), 5 jours » ; vide si rien n'est planifiable.
export function scheduleLine(schedule) {
  if (!schedule || !schedule.first_at) return "";
  const days = (schedule.days || []).length;
  const total = (schedule.days || []).reduce((n, d) => n + d.count, 0);
  const first = formatSlot(schedule.first_at, schedule.timezone);
  const last = formatSlot(schedule.last_at, schedule.timezone);
  return `${plural(total, "message")}, du ${first} au ${last} (heures : ${schedule.timezone}), ${plural(days, "jour")}`;
}

// Le bouton final : « Planifier les messages approuvés ». Il n'est actif que pour un rôle qui décide, avec au moins un message
// réellement envoyable et aucun blocage ; la raison d'un refus est donnée, jamais un bouton muet.
export const PLAN_BUTTON = "Planifier les messages approuvés";

export function planButton({ plan, canDecide, busy }) {
  if (!plan) return { disabled: true, reason: "Plan en cours de chargement…" };
  if (busy) return { disabled: true, reason: "Planification en cours…" };
  if (!canDecide) return { disabled: true, reason: "Seuls un propriétaire ou un administrateur peuvent planifier." };
  if (plan.blockers && plan.blockers.length) return { disabled: true, reason: plan.blockers[0].label };
  if (!plan.sendable) return { disabled: true, reason: "Aucun message approuvé et propre à planifier pour l'instant." };
  return { disabled: false, reason: null };
}

// Ce que dit la confirmation avant d'écrire le plan.
export function confirmText(plan) {
  if (!plan) return "";
  const dry = plan.gates && plan.gates.dry_run ? " L'envoi réel est désactivé : les messages seront simulés, rien ne partira." : "";
  return `Planifier ${plural(plan.sendable, "message")} (un par destinataire, sans copie ni copie cachée) ? ${scheduleLine(plan.schedule)}.${dry} Rien ne part maintenant : chaque message repasse toutes les portes au moment de son envoi.`;
}

// Les ids des brouillons qu'on peut approuver d'un geste : en attente de relecture et sans point bloquant.
export const hasBlocking = (row) => (row.problems || []).some((p) => p.blocking);

export function approvableIds(items) {
  return (items || []).filter((r) => r.stage === "to_review" && r.draft && !hasBlocking(r)).map((r) => r.draft.id);
}

// Réponse de POST /review-drafts -> une phrase.
export function reviewResultText(result, decision) {
  if (!result) return "";
  const verb = decision === "approve" ? "approuvé" : "rejeté";
  const done = result.done || 0;
  const refused = result.refused || 0;
  const base = done ? `${plural(done, "brouillon")} ${verb}${done > 1 ? "s" : ""}` : "Aucun brouillon modifié";
  if (!refused) return `${base}.`;
  const first = (result.results || []).find((r) => !r.ok);
  return `${base} ; ${plural(refused, "refusé")}${first && first.reason ? ` (${first.reason})` : ""}.`;
}

// Une erreur de l'écran, en une phrase. Le 409 « le plan a changé » demande de relire avant de recommencer.
export function launchError(err) {
  const response = err && err.response;
  if (!response) return "Le serveur est injoignable. Vérifiez votre connexion puis réessayez.";
  const detail = response.data && response.data.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    if (detail.code === "plan_changed") return `${detail.message} Le plan affiché a été rechargé : relisez-le puis confirmez.`;
    return detail.message || `Refusé (${detail.code || response.status}).`;
  }
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d && d.msg) || String(d)).join(" ; ");
  return `La requête a échoué (${response.status}).`;
}

export const isPlanChanged = (err) => {
  const detail = err && err.response && err.response.data && err.response.data.detail;
  return Boolean(detail && typeof detail === "object" && detail.code === "plan_changed");
};

// Le badge d'autorisation du canal dit la BASE réelle du destinataire, jamais un « autorisé » sec : sans opt-in ni consentement
// déclaré, un contact n'est pas présenté comme ayant accepté une campagne, même si le fournisseur ne le bloque pas.
export const BASIS_CHIP = {
  opt_in: { label: "Opt-in enregistré", chip: "chip-success" },
  declared_consent: { label: "Consentement déclaré à l'import", chip: "chip-success" },
  legitimate_interest_b2b: { label: "Intérêt légitime, sans opt-in", chip: "chip-warn" },
  public_directory: { label: "Annuaire public, sans opt-in", chip: "chip-warn" },
};

export function authorizationChip(auth) {
  if (!auth || !auth.ok) return { label: "Canal non autorisé", chip: "chip-danger" };
  return BASIS_CHIP[auth.basis] || { label: "Base inconnue", chip: "chip-warn" };
}

// Ce que le fournisseur autorise : un texte pour l'opérateur, jamais une valeur secrète. « Un quota disponible ne vaut pas
// autorisation » est affiché dès que le fournisseur impose ou ignore une règle.
export const COLD_OUTREACH = {
  opt_in_required: { label: "Opt-in explicite requis", chip: "chip-danger" },
  unverified: { label: "Conditions non vérifiées", chip: "chip-warn" },
  not_configured: { label: "Aucun fournisseur configuré", chip: "chip-ink" },
};

export function providerNotice(gates) {
  if (!gates) return null;
  const meta = COLD_OUTREACH[gates.provider.cold_outreach] || COLD_OUTREACH.unverified;
  const label = gates.provider.label === meta.label ? meta.label : `${gates.provider.label} — ${meta.label}`;
  return { ...meta, label, restriction: gates.provider.restriction };
}

// Les états des portes d'envoi, sous forme de pastilles lisibles. Rien n'est déduit : chaque pastille reprend un booléen du serveur.
export function gateChips(gates) {
  if (!gates) return [];
  const chips = [
    gates.dry_run
      ? { key: "dry_run", label: "Simulation (dry-run) : rien ne part", chip: "chip-cold" }
      : { key: "live", label: "Envoi réel activé", chip: "chip-warn" },
  ];
  if (!gates.dry_run) chips.push(gates.sandbox ? { key: "sandbox", label: `Bac à sable : ${gates.allowlist_size} adresse(s) autorisée(s)`, chip: "chip-warn" } : { key: "sandbox_off", label: "Bac à sable désactivé", chip: "chip-danger" });
  if (gates.kill_switch) chips.push({ key: "kill_switch", label: "Arrêt d'urgence actif", chip: "chip-danger" });
  if (gates.paused) chips.push({ key: "paused", label: "Envois en pause", chip: "chip-danger" });
  if (!gates.sender_configured) chips.push({ key: "sender", label: "Identité d'expéditeur manquante", chip: "chip-danger" });
  return chips;
}

export function limitsLine(gates) {
  if (!gates) return "";
  const zone = gates.timezone_source === "lead_country" ? "dans le fuseau de chaque destinataire" : `(${gates.timezone})`;
  return `${gates.max_per_day} par jour · ${gates.max_per_hour} par heure · ${gates.min_delay_seconds} s minimum entre deux messages · fenêtre ${gates.window_start_hour} h–${gates.window_end_hour} h ${zone} · jours comptés en ${gates.timezone} · aujourd'hui : ${gates.sent_today} envoyé(s)`;
}

// Le planificateur (worker + beat) : sans lui, le plan est écrit mais rien ne part. L'écran le dit au lieu de l'espérer.
export function schedulerNotice(scheduler) {
  if (!scheduler || !scheduler.checked) return { ok: false, text: "Impossible de vérifier le worker : le plan s'exécute seulement si un worker et le beat tournent." };
  if (scheduler.worker_ok && scheduler.beat_ok) return { ok: true, text: "Worker et beat détectés : le plan sera exécuté." };
  const missing = [!scheduler.worker_ok && "worker", !scheduler.beat_ok && "beat"].filter(Boolean).join(" et ");
  return { ok: false, text: `Aucun ${missing} détecté : le plan serait écrit mais aucun message ne partirait (voir docs/campaign-launch.md).` };
}

// Pourcentage d'avancement d'une campagne : accepté, simulé ou répondu / total. Vide si rien n'est planifié.
export function progress(counts) {
  const total = Object.values(counts || {}).reduce((n, v) => n + v, 0);
  if (!total) return null;
  const done = ["accepted", "simulated", "replied", "opted_out", "bounced", "failed", "unknown", "skipped", "cancelled"].reduce((n, k) => n + ((counts || {})[k] || 0), 0);
  return { total, done, percent: Math.round((done / total) * 100) };
}

// Les brouillons encore à produire, par état de leur préparation automatique : « 3 en file · 1 en attente de l'IA ».
export const JOB_FR = {
  queued: "en file",
  generating: "en cours d'écriture",
  unavailable: "en attente de l'IA",
  offer_required: "en attente de votre offre",
  failed: "en échec",
  ready: "prêts",
};

export function jobLine(jobs) {
  const parts = Object.keys(JOB_FR)
    .filter((k) => (jobs || {})[k] > 0)
    .map((k) => `${jobs[k]} ${JOB_FR[k]}`);
  return parts.join(" · ");
}
