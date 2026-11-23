// Pure formatting for the dashboard. "null" from the API means "nothing known yet": it is shown as an em dash, never as 0.

export const DASH = "—";

export const pct = (rate) => (rate === null || rate === undefined ? DASH : `${Math.round(rate * 1000) / 10}%`);
export const num = (n) => (n === null || n === undefined ? DASH : String(n));

// Five numbers that help decide, nothing decorative. "Hot" is the server's decision (qualified AND an observed, sourced
// intent), never a score; no money value is estimated. A null is "not known yet", shown as a dash.
export function kpiCards(k, limits) {
  return [
    { key: "prospects", label: "Prospects", value: num(k.prospects), hint: `${k.pending_review || 0} à relire · ${k.approved || 0} approuvés`, accent: "blue" },
    { key: "hot_leads", label: "Hot", value: num(k.hot_leads), hint: "intention commerciale observée et sourcée", accent: "amber" },
    {
      key: "sent_today", label: "Envoyés aujourd'hui", value: num(k.sent_today),
      hint: `${limits.remaining_today ?? DASH} restant(s) sur ${limits.max_per_day ?? DASH}`, accent: "cyan",
    },
    { key: "replies", label: "Réponses", value: num(k.replies), hint: k.reply_rate === null ? "aucun message envoyé" : `${pct(k.reply_rate)} de ${k.messages} envoyé(s)`, accent: "violet" },
    { key: "unsubscribed", label: "Désinscriptions", value: num(k.unsubscribed), hint: "sur la liste d'opposition", accent: "leaf" },
  ];
}

// The e-mail channel a live send would take, as the server decided it (Resend, then Brevo, then SMTP); an older answer
// without the field falls back to SMTP alone. Null: no channel, nothing can leave.
export const CHANNEL_LABELS = { resend: "Resend", brevo: "Brevo", smtp: "SMTP" };
export function channelOf(l) {
  const id = l.email_channel !== undefined ? l.email_channel : l.smtp_configured ? "smtp" : null;
  return id ? CHANNEL_LABELS[id] || id : null;
}

// Sending mode as an operator should read it. The order matters: the most restrictive state wins.
export function modeOf(l) {
  if (l.kill_switch) return { tone: "danger", label: "ARRÊT D'URGENCE" };
  if (l.paused) return { tone: "warn", label: "EN PAUSE" };
  if (l.dry_run) return { tone: "ink", label: "SIMULATION" };
  if (!channelOf(l)) return { tone: "danger", label: "RÉEL · AUCUN CANAL E-MAIL" };
  if (l.sandbox) return { tone: "warn", label: `RÉEL · BAC À SABLE (${l.allowlist_size} AUTORISÉ${l.allowlist_size > 1 ? "S" : ""})` };
  return { tone: "danger", label: "RÉEL · OUVERT" };
}

export function quotaShare(l) {
  return l.max_per_day > 0 ? Math.min(1, l.sent_today / l.max_per_day) : 1;
}

export const seriesHasData = (series) => (series || []).some((p) => p.sent > 0 || p.replied > 0 || p.acquired > 0);

export function seriesSummary(series) {
  if (!series || !series.length) return "No series data available";
  const sent = series.reduce((a, p) => a + (p.sent || 0), 0);
  const replied = series.reduce((a, p) => a + (p.replied || 0), 0);
  return `${sent} message${sent === 1 ? "" : "s"} sent and ${replied} repl${replied === 1 ? "y" : "ies"} over the last ${series.length} days (UTC)`;
}

export function shortDay(iso) {
  if (!iso) return "";
  const parts = iso.split("-");
  if (parts.length < 3) return iso;
  const [, m, d] = parts;
  return `${d}/${m}`;
}

export function ago(iso, now = new Date()) {
  if (!iso) return DASH;
  const s = Math.max(0, Math.round((now - new Date(iso)) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// Geometry of SVG activity & acquisition charts, pure and testable
export function chartGeometry(series, { width = 600, height = 220, left = 32, right = 8, top = 8, bottom = 22 } = {}) {
  const count = (series || []).length;
  if (count === 0) {
    return { max: 1, ticks: [0, 1], x: () => 0, y: () => 0, line: () => "", area: () => "", baseline: 0, width, height };
  }
  const max = Math.max(1, ...series.map((p) => Math.max(p.sent || 0, p.replied || 0, p.acquired || 0)));
  const step = Math.max(1, Math.ceil(max / 4));
  const top_ = step * Math.ceil(max / step);
  const ticks = [];
  for (let v = 0; v <= top_; v += step) ticks.push(v);
  const x = (i) => left + (count <= 1 ? 0 : (i * (width - left - right)) / (count - 1));
  const y = (v) => top + (1 - (v || 0) / top_) * (height - top - bottom);
  const pts = (key) => series.map((p, i) => `${x(i).toFixed(1)},${y(p[key] || 0).toFixed(1)}`);
  return {
    max: top_,
    ticks,
    x,
    y,
    line: (key) => pts(key).join(" "),
    area: (key) => [`${x(0).toFixed(1)},${y(0).toFixed(1)}`, ...pts(key), `${x(count - 1).toFixed(1)},${y(0).toFixed(1)}`].join(" "),
    baseline: y(0),
    width,
    height,
  };
}
