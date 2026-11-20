// Pure formatting of the credits and outreach models (GET /usage/credits). Every number comes from the server.

const pad = (n) => String(n).padStart(2, "0");

// "dans 2 h 14 min" / "dans 12 min" / "maintenant"
export function untilText(iso, now = new Date()) {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - now.getTime();
  if (!(ms > 0)) return "maintenant";
  const minutes = Math.ceil(ms / 60000);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `dans ${h} h${m ? ` ${pad(m)} min` : ""}` : `dans ${m} min`;
}

export const clockText = (iso) => new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });

// One bar of the meter: the share used (0–100), what is left, and when it resets.
export function meter(w, now = new Date()) {
  const limit = Number(w.limit) || 0;
  const used = Number(w.used) || 0;
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100;
  const tone = pct >= 100 ? "danger" : pct >= 80 ? "warn" : "ok";
  let reset;
  if (w.resets_at) reset = `Réinitialisation ${untilText(w.resets_at, now)} (${clockText(w.resets_at)})`;
  else if (w.key === "session") reset = "Aucune session en cours : elle commence à la prochaine utilisation.";
  else reset = "Rien d'utilisé aujourd'hui.";
  return { pct, tone, used, limit, remaining: Math.max(0, limit - used), label: `${used} / ${limit} crédits`, reset };
}

// The tightest window: what the sidebar shows in one line.
export function tightest(windows) {
  const list = (windows || []).filter((w) => Number(w.limit) > 0);
  if (!list.length) return null;
  return list.reduce((a, b) => (b.used / b.limit > a.used / a.limit ? b : a));
}

export const costText = (m) => (m.credits === 0 ? "0 crédit · sans IA" : `${m.credits} crédit${m.credits > 1 ? "s" : ""} par message`);

// How many messages are left with a model, given the tightest remaining window ("∞" for a model that costs nothing).
export function messagesLeft(m, windows) {
  if (!m || m.credits === 0) return "illimité (aucun appel à l'IA)";
  const remaining = Math.min(...(windows || []).map((w) => Math.max(0, w.limit - w.used)));
  if (!Number.isFinite(remaining)) return "—";
  const n = Math.floor(remaining / m.credits);
  return `${n} message${n === 1 ? "" : "s"} possible${n === 1 ? "" : "s"} maintenant`;
}

// Today's real AI usage (GET /usage/credits → ai_usage), one line per model that really answered. The tokens are the
// provider's own count: a total it did not report is said so, never shown as 0 or estimated. Null: nothing used today.
const fmt = (n) => Number(n).toLocaleString("fr-FR");
export function aiUsageLines(usage) {
  const models = (usage && usage.models) || [];
  const unattributed = (usage && usage.unattributed) || 0;
  if (!models.length && !unattributed) return null;
  const lines = models.map((m) => {
    const requests = `${m.spends} demande${m.spends === 1 ? "" : "s"}`;
    let tokens;
    if (m.tokens === null || m.tokens === undefined) tokens = "tokens non rapportés";
    else if (m.without_tokens) tokens = `au moins ${fmt(m.tokens)} tokens (${m.without_tokens} sans chiffre du fournisseur)`;
    else tokens = `${fmt(m.tokens)} tokens`;
    return { key: m.ai_model, model: m.ai_model, text: `${requests} · ${tokens}` };
  });
  if (unattributed) {
    lines.push({ key: "unattributed", model: "modèle non enregistré", text: `${unattributed} demande${unattributed === 1 ? "" : "s"} · tokens non rapportés` });
  }
  return lines;
}
