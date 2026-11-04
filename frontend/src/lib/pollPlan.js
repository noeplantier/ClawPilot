// When a live view asks the server again. Pure: the clock and the page visibility are injected.
//
// Idle, a page refreshes every BASE_MS; for BURST_WINDOW_MS after something the person (or the server) just started — a
// search, an addition, a draft being prepared — it refreshes every BURST_MS, so a prospect that became eligible shows
// within about two seconds. A hidden tab is not asked at all (it refreshes the moment it is shown again) and a failing
// server is asked less often, never harder. A 304 answer costs the server one query and the network almost nothing.
export const BASE_MS = 10000;
export const BURST_MS = 2000;
export const BURST_WINDOW_MS = 120000;
export const HIDDEN_RECHECK_MS = 30000;
export const MAX_BACKOFF_MS = 60000;
export const SECONDARY_EVERY = 3; // counters that change slowly (towns) ride on every third refresh

export function nextDelay({ now, burstUntil = 0, hidden = false, failures = 0 }) {
  if (hidden) return HIDDEN_RECHECK_MS;
  const base = now < burstUntil ? BURST_MS : BASE_MS;
  return failures > 0 ? Math.min(MAX_BACKOFF_MS, base * 2 ** Math.min(failures, 5)) : base;
}

// A burst never shortens one that is already running.
export const startBurst = (now, current = 0, windowMs = BURST_WINDOW_MS) => Math.max(current, now + windowMs);

// Whether the slow counters ride on this refresh (the first one always loads them).
export const withSecondary = (tick) => tick % SECONDARY_EVERY === 0;
