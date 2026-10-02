// Pure helpers for the OutreachOS screens: no React, no network, no clock (callers pass `now`).
// Everything shown on screen comes from the API; these only format and explain it.

export const STATE_META = {
  detected: { label: "Detected", chip: "chip-ink", glyph: "●", hint: "The observation was made and matches the signal." },
  not_detected: { label: "Not detected", chip: "chip-success", glyph: "○", hint: "The observation was made and says the opposite." },
  unknown: { label: "Unknown", chip: "chip", glyph: "?", hint: "It could not be observed. This never counts for or against a prospect." },
};

export const REVIEW_META = {
  pending: { label: "Pending review", chip: "chip-warn" },
  approved: { label: "Approved", chip: "chip-success" },
  rejected: { label: "Rejected", chip: "chip-danger" },
};

export const MESSAGE_STATUS_CHIP = { sending: "chip-warn", sent: "chip-ink", failed: "chip-danger", bounced: "chip-danger", replied: "chip-success" };

export function scoreBand(score) {
  if (score === null || score === undefined) return "none";
  if (score >= 60) return "high";
  if (score >= 30) return "medium";
  return "low";
}

// Sum of points vs the 0-100 clamp, so a reviewer can see why 120 raw points shows as 100.
export function explainTotal(breakdown) {
  const lines = breakdown || [];
  const raw = lines.reduce((sum, l) => sum + (l.points || 0), 0);
  const capped = Math.max(0, Math.min(100, raw));
  const weighted = lines.filter((l) => l.weight !== 0);
  const observed = weighted.filter((l) => l.state !== "unknown");
  return { raw, capped, clamped: raw !== capped, weighted: weighted.length, observed: observed.length };
}

export function coverageLabel(coverage) {
  if (coverage === null || coverage === undefined) return "—";
  return `${Math.round(coverage * 100)}%`;
}

export function domainOf(url) {
  if (!url) return null;
  try {
    return new URL(url.includes("//") ? url : `//${url}`, "http://x").hostname.replace(/^www\./, "") || null;
  } catch (e) {
    return null;
  }
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export function formatRetry(retryAt, now = new Date()) {
  if (!retryAt) return null;
  const at = new Date(retryAt);
  if (Number.isNaN(at.getTime())) return null;
  const minutes = Math.max(0, Math.ceil((at.getTime() - now.getTime()) / 60000));
  const when = at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (minutes < 1) return `now (${when})`;
  if (minutes < 120) return `in ${minutes} min (${when})`;
  return `in ${Math.round(minutes / 60)} h (${when})`;
}

// What a refused dispatch means, in words the operator can act on. Codes come from services/outreach_os/dispatch.py.
const BLOCK_TEXT = {
  kill_switch: "Sending is halted by the kill switch (SEND_KILL_SWITCH). Someone with deploy access must clear it.",
  paused: "Sending is paused for this organisation. Resume it on the Sending page.",
  limit_daily: "The daily limit is reached.",
  limit_hourly: "The hourly limit is reached.",
  limit_delay: "The minimum delay between two messages has not elapsed yet.",
  draft_not_approved: "A human must approve the draft first.",
  prospect_not_approved: "The prospect is no longer approved.",
  suppressed: "This prospect is on the suppression list (opted out, bounced or erased).",
  opted_out: "This prospect opted out of e-mail.",
  no_email: "This prospect has no e-mail address.",
  sender_not_configured: "The sender identity is not configured on the server (OUTREACH_SENDER_*).",
  not_compliant: "The draft is missing a mandatory element (sender, data origin or unsubscribe link).",
  live_not_available: "Real sending is not available: live sending is off, or the SMTP settings are incomplete. Nothing was sent.",
  sandbox_recipient: "Sandbox is on: this recipient is not on OUTREACH_LIVE_ALLOWLIST. Nothing was sent.",
  not_simulated: "Only dry-run messages can be simulated.",
  already_bounced: "This message already bounced.",
  not_delivered: "This message was never sent.",
};

// What a test e-mail result means. "sent" only says the SMTP server accepted it, not that it reached an inbox.
export function describeTestSend(result) {
  if (result.status === "sent") {
    return {
      tone: "ok",
      text: `Accepted by the SMTP server for ${result.to}. Check the inbox and the spam folder, then open the original message: SPF, DKIM and DMARC should read "pass".`,
    };
  }
  if (result.status === "unknown") {
    return { tone: "warn", text: `Outcome unknown (${result.error}). Check the mailbox's Sent folder before trying again.` };
  }
  return { tone: "danger", text: `Not sent: ${result.error || "the SMTP server refused the message"}` };
}

export function blockText(code) {
  return BLOCK_TEXT[code] || null;
}

// Turn an axios error into one readable sentence. Handles string details, {code, message, retry_at} objects,
// FastAPI validation arrays and network failures.
export function describeApiError(err, now = new Date()) {
  const response = err && err.response;
  if (!response) return "Cannot reach the server. Check your connection and try again.";
  const detail = response.data && response.data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && d.msg ? `${(d.loc || []).slice(1).join(".") || "input"}: ${d.msg}` : String(d))).join("; ");
  }
  if (detail && typeof detail === "object") {
    const base = blockText(detail.code) || detail.message || `Request refused (${detail.code || response.status})`;
    const retry = formatRetry(detail.retry_at, now);
    return retry ? `${base} You can try again ${retry}.` : base;
  }
  return `Request failed (${response.status}).`;
}

const AUDIT_LABEL = {
  "prospect.created": "Discovered",
  "prospect.approved": "Approved by a reviewer",
  "prospect.rejected": "Rejected by a reviewer",
  "prospect.opted_out": "Opted out (unsubscribe link)",
  "prospect.erased": "Erased",
  "draft.created": "Draft prepared",
  "draft.approved": "Draft approved",
  "draft.rejected": "Draft rejected",
  "message.dispatched": "Dispatched (dry-run)",
  "message.failed": "Dispatch failed",
  "message.bounced": "Bounce recorded",
  "message.replied": "Reply recorded",
  "send.blocked_review": "Send refused: review status",
  "send.blocked_consent": "Send refused: no consent",
};
const MESSAGE_EVENT_LABEL = {
  sent: "Adapter accepted the message (dry-run)",
  failed: "Message failed",
  bounced: "Hard bounce",
  replied: "Reply received",
  opted_out: "Opted out by reply",
};

export function auditLabel(action, detail) {
  if (action === "dispatch.blocked") return `Dispatch refused${detail && detail.code ? `: ${detail.code}` : ""}`;
  return AUDIT_LABEL[action] || action;
}

// Merge the prospect's audit trail and its messages' events into one list, newest first.
export function mergeTimeline(auditEvents, messages, currentUserId) {
  const items = [];
  (auditEvents || []).forEach((e) =>
    items.push({
      key: `a-${e.id}`,
      at: e.created_at,
      label: auditLabel(e.action, e.detail),
      actor: e.actor_user_id ? (e.actor_user_id === currentUserId ? "you" : "another user") : e.actor_type,
      detail: e.detail || {},
      kind: "audit",
    })
  );
  (messages || []).forEach((m) =>
    (m.events || []).forEach((e) =>
      items.push({
        key: `m-${e.id}`,
        at: e.created_at,
        label: MESSAGE_EVENT_LABEL[e.event_type] || e.event_type,
        actor: "provider (simulated)",
        detail: e.detail || {},
        kind: "message",
      })
    )
  );
  return items.sort((a, b) => new Date(b.at) - new Date(a.at));
}

// Short "key: value" summary of an audit/event detail object, for display only.
export function detailSummary(detail) {
  return Object.entries(detail || {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && typeof v !== "object")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(" · ");
}

export const LIMIT_RANGES = {
  max_per_day: { min: 0, max: 100000, label: "Messages per day" },
  max_per_hour: { min: 0, max: 100000, label: "Messages per hour" },
  min_delay_seconds: { min: 0, max: 86400, label: "Minimum delay between messages (seconds)" },
};

// Returns an error message per invalid field (empty object = valid). Mirrors the API ranges.
export function validateLimits(values) {
  const errors = {};
  Object.entries(LIMIT_RANGES).forEach(([key, { min, max, label }]) => {
    const raw = values[key];
    const n = Number(raw);
    if (raw === "" || raw === null || raw === undefined || !Number.isInteger(n)) errors[key] = `${label}: enter a whole number`;
    else if (n < min || n > max) errors[key] = `${label}: must be between ${min} and ${max}`;
  });
  return errors;
}

// Only the fields that changed, as numbers, so the PUT does not rewrite untouched limits.
export function limitsPatch(original, values) {
  const patch = {};
  Object.keys(LIMIT_RANGES).forEach((key) => {
    if (Number(values[key]) !== Number(original[key])) patch[key] = Number(values[key]);
  });
  return patch;
}
