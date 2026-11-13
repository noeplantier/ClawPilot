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
