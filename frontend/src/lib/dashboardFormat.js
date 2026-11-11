// Pure formatting for the dashboard. "null" from the API means "nothing known yet": it is shown as an em dash, never as 0.

export const DASH = "—";

export const pct = (rate) => (rate === null || rate === undefined ? DASH : `${Math.round(rate * 1000) / 10}%`);
export const num = (n) => (n === null || n === undefined ? DASH : String(n));

export function kpiCards(k, limits) {
  const cards = [
    { key: "prospects", label: "Total Prospects", value: num(k.prospects), hint: `${k.pending_review || 0} pending review · ${k.approved || 0} approved`, accent: "blue" },
    {
      key: "avg_score", label: "Average Score", value: k.avg_score === null ? DASH : `${k.avg_score}`,
      hint: k.scored ? `over ${k.scored} scored prospect${k.scored === 1 ? "" : "s"}` : "nothing scored yet", accent: "violet",
    },
    {
      key: "sent_today", label: "Sent Today", value: num(k.sent_today),
      hint: `${limits.remaining_today ?? DASH} left of ${limits.max_per_day ?? DASH} allowed`, accent: "cyan",
    },
    { key: "replies", label: "Replies", value: num(k.replies), hint: k.reply_rate === null ? "no message sent yet" : `${pct(k.reply_rate)} of ${k.messages} sent`, accent: "blue" },
    { key: "bounces", label: "Bounces", value: num(k.bounces), hint: k.bounce_rate === null ? "no message sent yet" : `${pct(k.bounce_rate)} of ${k.messages} sent`, accent: "violet" },
    { key: "unsubscribed", label: "Unsubscribed", value: num(k.unsubscribed), hint: "addresses on do-not-contact list", accent: "cyan" },
  ];

  // Extended KPIs matching the Plantiers Mandate
  if (k.hot_leads !== undefined || k.qualified_leads !== undefined || k.emails_available !== undefined) {
    cards.push(
      { key: "qualified_leads", label: "Qualified Leads", value: num(k.qualified_leads ?? k.approved), hint: "verified & approved for outreach", accent: "leaf" },
      { key: "hot_leads", label: "Hot Leads", value: num(k.hot_leads), hint: "high score with full contacts", accent: "amber" },
      { key: "emails_available", label: "Emails Available", value: num(k.emails_available), hint: "verified business email contacts", accent: "blue" },
      { key: "phones_available", label: "WhatsApp Ready", value: num(k.phones_available), hint: "verified telephone contacts", accent: "leaf" },
      { key: "conversion_rate", label: "Conversion Rate", value: k.reply_rate === null ? DASH : pct(k.reply_rate), hint: "reply & response performance", accent: "violet" },
      { key: "pipeline_value", label: "Est. Pipeline Value", value: k.pipeline_value ? `${k.pipeline_value.toLocaleString()} €` : DASH, hint: "projected value of qualified pipeline", accent: "leaf" }
    );
  }

  return cards;
}

// Sending mode as an operator should read it. The order matters: the most restrictive state wins.
export function modeOf(l) {
  if (l.kill_switch) return { tone: "danger", label: "HALTED · KILL SWITCH" };
  if (l.paused) return { tone: "warn", label: "PAUSED" };
  if (l.dry_run) return { tone: "ink", label: "DRY-RUN" };
  if (!l.smtp_configured) return { tone: "danger", label: "LIVE FLAG ON · SMTP INCOMPLETE" };
  if (l.sandbox) return { tone: "warn", label: `LIVE · SANDBOX (${l.allowlist_size} ALLOWED)` };
  return { tone: "danger", label: "LIVE · OPEN" };
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
