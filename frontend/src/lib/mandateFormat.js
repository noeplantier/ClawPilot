// Formatage pur de l'écran « Automatisation max » : le mode est borné, désactivé par défaut, et tout ce qui s'affiche
// vient du serveur. Aucune valeur par défaut n'est inventée ici : les plafonds et les limites sont ceux de la réponse.
import { formatDateTime } from "@/lib/outreachFormat";

// Les quatre phrases à cocher, dans les mots de l'autorisation (le serveur les attend par leur code).
export const ACK_TEXT = {
  bounded: "Je comprends que le mandat n'agit que dans sa zone, avec ce message, cet expéditeur, ces plafonds et jusqu'à son expiration : rien d'autre.",
  real_sending: "Je comprends que les messages partent pour de vrai quand l'envoi réel est activé sur ce serveur.",
  provider_terms: "Je sais que les conditions du fournisseur d'envoi et la loi sur la prospection sont deux vérifications distinctes, et que je les ai faites.",
  can_revoke: "Je sais que je peux révoquer à tout instant, et que ce qui est déjà parti ne peut pas être rappelé.",
};

export const STATUS = {
  draft: { label: "Brouillon : rien n'agit encore", tone: "chip-ink" },
  active: { label: "Actif", tone: "chip-success" },
  suspended: { label: "En pause", tone: "chip-warn" },
  revoked: { label: "Révoqué", tone: "chip-danger" },
  expired: { label: "Expiré", tone: "chip-ink" },
};
export const statusOf = (status) => STATUS[status] || { label: status, tone: "chip-ink" };

const ACTION = {
  created: "Mandat créé",
  activated: "Autorisation donnée",
  suspended: "Mis en pause",
  revoked: "Révoqué",
  expired: "Expiré",
  held: "Rien envoyé ce tour-ci",
  run: "Tour d'exécution",
  revalidated: "Revalidé après un changement",
  activation_refused: "Activation refusée",
};

export function journalLine(event, labels = {}) {
  const base = ACTION[event.action] || event.action;
  const d = event.detail || {};
  const reason = d.reason || d.code;
  const why = reason ? ` : ${labels[reason] || reason}` : "";
  const sent = typeof d.sent === "number" ? ` · ${d.sent} envoyé${d.sent === 1 ? "" : "s"}` : "";
  return `${formatDateTime(event.at)} · ${base}${why}${sent} · ${event.actor === "user" ? "par une personne" : "automatique"}`;
}

// Le formulaire : démarre prudent (le plus petit des plafonds permis), borné par les limites du serveur.
export function formDefaults(limits, campaign) {
  const cap = Math.min(limits.max_daily, 20);
  return {
    name: campaign ? `Mandat · ${campaign.name}`.slice(0, 120) : "Mandat d'automatisation",
    daily_cap: cap,
    total_cap: Math.min(limits.max_total, 100),
    days: Math.min(limits.max_days, 14),
    window_start_hour: 8,
    window_end_hour: 18,
    min_delay_seconds: Math.max(limits.min_delay_seconds, 60),
    search_every_hours: Math.max(limits.min_search_hours, 24),
    ai_budget: 0,
    max_bounce_rate: 0.05,
    max_opt_out_rate: 0.1,
    min_sample: 20,
  };
}

export function validateForm(f, limits) {
  const errors = {};
  const within = (key, lo, hi, label) => {
    const v = Number(f[key]);
    if (!Number.isInteger(v) || v < lo || v > hi) errors[key] = `${label} : un entier de ${lo} à ${hi}.`;
  };
  within("daily_cap", 1, limits.max_daily, "Plafond par jour");
  within("total_cap", 1, limits.max_total, "Plafond total");
  within("days", 1, limits.max_days, "Durée en jours");
  within("min_delay_seconds", limits.min_delay_seconds, 3600, "Délai entre deux messages (s)");
  within("search_every_hours", limits.min_search_hours, 168, "Fréquence de recherche (h)");
  within("ai_budget", 0, 1000, "Budget IA");
  if (!errors.window_start_hour && !(Number(f.window_start_hour) >= 0 && Number(f.window_start_hour) < Number(f.window_end_hour) && Number(f.window_end_hour) <= 24)) errors.window_start_hour = "La fenêtre d'envoi doit commencer avant de finir (0 à 24 h).";
  if (!errors.daily_cap && !errors.total_cap && Number(f.daily_cap) > Number(f.total_cap)) errors.daily_cap = "Le plafond par jour ne peut pas dépasser le plafond total.";
  if (!(Number(f.max_bounce_rate) > 0 && Number(f.max_bounce_rate) <= 0.1)) errors.max_bounce_rate = "Rebonds : au plus 10 % (0,01 à 0,10).";
  if (!(Number(f.max_opt_out_rate) > 0 && Number(f.max_opt_out_rate) <= 0.2)) errors.max_opt_out_rate = "Oppositions : au plus 20 % (0,01 à 0,20).";
  return errors;
}

export const toPayload = (f, campaignId) => ({
  campaign_id: campaignId,
  name: String(f.name).trim(),
  daily_cap: Number(f.daily_cap),
  total_cap: Number(f.total_cap),
  days: Number(f.days),
  window_start_hour: Number(f.window_start_hour),
  window_end_hour: Number(f.window_end_hour),
  min_delay_seconds: Number(f.min_delay_seconds),
  search_every_hours: Number(f.search_every_hours),
  ai_budget: Number(f.ai_budget),
  stop_rules: { max_bounce_rate: Number(f.max_bounce_rate), max_opt_out_rate: Number(f.max_opt_out_rate), min_sample: Number(f.min_sample) },
});

// Ce qui empêche d'activer maintenant, en une phrase ; null = les quatre cases sont cochées et le serveur autorise le mode.
export function activationBlock(overview, acked) {
  if (!overview.enabled) return overview.why_disabled || "Le mode automatique est désactivé sur ce serveur.";
  if (!overview.reply_collection_configured) return "Les réponses ne sont pas lues (IMAP non configuré) : une opposition passerait inaperçue, le serveur refusera.";
  const missing = overview.acknowledgements.filter((code) => !acked.includes(code));
  if (missing.length) return `Cochez les ${missing.length} confirmation${missing.length === 1 ? "" : "s"} restante${missing.length === 1 ? "" : "s"} : l'autorisation est explicite.`;
  return null;
}

export const remainingLine = (report) =>
  report && report.remaining ? `Il reste ${report.remaining.messages} message${report.remaining.messages === 1 ? "" : "s"} et ${report.remaining.days} jour${report.remaining.days === 1 ? "" : "s"} avant l'expiration.` : "";
