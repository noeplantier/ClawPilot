// "Live" data without a socket (none on the free host): fetch, then fetch again every few seconds while the tab is visible.
// A failed refresh keeps what is on screen and says so; only the very first load can end in an error.
import { useCallback, useEffect, useRef, useState } from "react";
import { describeApiError } from "@/lib/outreachFormat";
import * as swr from "@/lib/swr";

export const LIVE_MS = 15000;

// Ids that appeared since the previous fetch ("new" rows are highlighted, never silently inserted).
export function freshIds(previous, next, idOf) {
  if (!previous || !Array.isArray(previous) || !Array.isArray(next)) return new Set();
  const seen = new Set(previous.map(idOf));
  return new Set(next.filter((x) => !seen.has(idOf(x))).map(idOf));
}

// `key` turns on the data cache (lib/swr.js): the last answer for that key is on screen at once while the server is asked again.
export function useLive(fn, deps, { intervalMs = LIVE_MS, idOf = (x) => x.id, itemsOf = (d) => d, key = null } = {}) {
  const [state, setState] = useState(() => {
    const hit = swr.read(key);
    return { data: hit ? hit.data : null, error: null, loading: !hit, updatedAt: hit ? new Date(hit.at) : null, stale: false, fresh: new Set() };
  });
  const keyRef = useRef(key);
  keyRef.current = key;
  const previous = useRef(null);
  const ticket = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);

  const load = useCallback(async (isPoll) => {
    const mine = ++ticket.current;
    if (!isPoll) {
      const cached = swr.read(keyRef.current);
      setState((s) => (cached
        ? { ...s, data: cached.data, error: null, loading: false, updatedAt: new Date(cached.at) }
        : { ...s, loading: true, error: null }));
    }
    try {
      const data = await run();
      if (mine !== ticket.current) return;
      swr.write(keyRef.current, data);
      const fresh = freshIds(previous.current, itemsOf(data), idOf);
      previous.current = itemsOf(data);
      setState({ data, error: null, loading: false, updatedAt: new Date(), stale: false, fresh });
    } catch (e) {
      if (mine !== ticket.current) return;
      setState((s) => (s.data ? { ...s, loading: false, stale: true } : { ...s, data: null, error: describeApiError(e), loading: false }));
    }
  }, [run]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    previous.current = null; // another query (a new search, a new filter): nothing is "new" yet
    load(false);
    const tick = () => { if (!document.hidden) load(true); };
    const id = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick); // back on the tab: refresh at once, not at the next tick
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", tick); ticket.current += 1; };
  }, [load, intervalMs]);

  const reload = useCallback(() => load(true), [load]);
  return { ...state, reload };
}
