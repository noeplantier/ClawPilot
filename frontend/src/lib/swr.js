// Stale-while-revalidate cache of what the API last answered: a page shows it at once, then refreshes it from the server.
// Memory first, sessionStorage behind it (a reload keeps it; closing the tab drops it). Cleared on sign-out and when the session
// ends, so one person's data is never shown to the next. Never a source of truth: every entry is replaced by the next answer.
const PREFIX = "outreachos.swr.v1:";
const MAX_CHARS = 400000; // one entry; a bigger answer stays in memory only
const memory = new Map();

const session = () => { try { return window.sessionStorage; } catch { return null; } }; // blocked storage: memory only

export function read(key) {
  if (!key) return null;
  if (memory.has(key)) return memory.get(key);
  const store = session();
  if (!store) return null;
  try {
    const raw = store.getItem(PREFIX + key);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    if (!entry || typeof entry.at !== "number" || !("data" in entry)) return null;
    memory.set(key, entry);
    return entry;
  } catch {
    return null;
  }
}

export function write(key, data) {
  if (!key || data === undefined) return;
  const entry = { data, at: Date.now() };
  memory.set(key, entry);
  const store = session();
  if (!store) return;
  try {
    const raw = JSON.stringify(entry);
    if (raw.length <= MAX_CHARS) store.setItem(PREFIX + key, raw);
    else store.removeItem(PREFIX + key);
  } catch { /* quota exceeded or blocked: the memory copy is enough */ }
}

export function clear() {
  memory.clear();
  const store = session();
  if (!store) return;
  try {
    Object.keys(store).filter((k) => k.startsWith(PREFIX)).forEach((k) => store.removeItem(k));
  } catch { /* nothing to clear */ }
}
