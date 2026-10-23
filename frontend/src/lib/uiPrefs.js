// Per-viewer interface preferences (sidebar folded, map panels hidden). Browser storage can be missing or throw
// (private window, blocked site data): every access is guarded and the page works without it.
const PREFIX = "pos.ui.";

export function readPref(key, fallback) {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writePref(key, value) {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the preference lasts for this visit only */
  }
}

// A key press must not toggle a panel while the user is typing in a field.
export function isTypingTarget(target) {
  if (!target || !target.tagName) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || Boolean(target.isContentEditable);
}
