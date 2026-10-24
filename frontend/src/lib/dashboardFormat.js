// Pure formatting for the dashboard. "null" from the API means "nothing known yet": it is shown as an em dash, never as 0.

export const DASH = "—";

export const pct = (rate) => (rate === null || rate === undefined ? DASH : `${Math.round(rate * 1000) / 10}%`);
export const num = (n) => (n === null || n === undefined ? DASH : String(n));

export function kpiCards(k, limits) {
  return [
    { key: "prospects", label: "Prospects", value: num(k.prospects), hint: `${k.pending_review} pending review · ${k.approved} approved`, accent: "blue" },
    {
      key: "avg_score", label: "Average score", value: k.avg_score === null ? DASH : `${k.avg_score}`,
      hint: k.scored ? `over ${k.scored} scored prospect${k.scored === 1 ? "" : "s"}` : "nothing scored yet", accent: "violet",
    },
    {
      key: "sent_today", label: "Sent today", value: num(k.sent_today),
      hint: `${limits.remaining_today} left of ${limits.max_per_day} allowed`, accent: "cyan",
    },
    { key: "replies", label: "Replies", value: num(k.replies), hint: k.reply_rate === null ? "no message sent yet" : `${pct(k.reply_rate)} of ${k.messages} sent`, accent: "blue" },
    { key: "bounces", label: "Bounces", value: num(k.bounces), hint: k.bounce_rate === null ? "no message sent yet" : `${pct(k.bounce_rate)} of ${k.messages} sent`, accent: "violet" },
    { key: "unsubscribed", label: "Unsubscribed", value: num(k.unsubscribed), hint: "addresses on the do-not-contact list", accent: "cyan" },
  ];
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

export const seriesHasData = (series) => series.some((p) => p.sent > 0 || p.replied > 0);

export function seriesSummary(series) {
  const sent = series.reduce((a, p) => a + p.sent, 0);
  const replied = series.reduce((a, p) => a + p.replied, 0);
  return `${sent} message${sent === 1 ? "" : "s"} sent and ${replied} repl${replied === 1 ? "y" : "ies"} over the last ${series.length} days (UTC)`;
}

export function shortDay(iso) {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export function ago(iso, now = new Date()) {
  const s = Math.max(0, Math.round((now - new Date(iso)) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// Geometry of the 14-day activity chart, pure so it can be tested: no charting library on the dashboard.
// -> { max, ticks, x(i), y(v), area(key), line(key) }. The vertical scale always starts at 0 and ends on an integer.
export function chartGeometry(series, { width = 600, height = 220, left = 32, right = 8, top = 8, bottom = 22 } = {}) {
  const count = series.length;
  const max = Math.max(1, ...series.map((p) => Math.max(p.sent, p.replied)));
  const step = Math.max(1, Math.ceil(max / 4));
  const top_ = step * Math.ceil(max / step);
  const ticks = [];
  for (let v = 0; v <= top_; v += step) ticks.push(v);
  const x = (i) => left + (count <= 1 ? 0 : (i * (width - left - right)) / (count - 1));
  const y = (v) => top + (1 - v / top_) * (height - top - bottom);
  const pts = (key) => series.map((p, i) => `${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`);
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
