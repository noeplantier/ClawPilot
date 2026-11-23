/* global AbortController */
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

// Per-mandate stream built on the same authenticated API as everything else (no Supabase Realtime, no JWT mismatch).
// `fetcher(since, signal)` returns a snapshot `{version, changed, ...}`; an unchanged poll keeps the current data.
// One timer, one in-flight request, one owner: stale requests are aborted, hidden tabs slow down and errors back off.
export const LIVE_FAST_MS = 2000;
export const LIVE_SLOW_MS = 15000;
export const LIVE_HIDDEN_MS = 60000;

export function useMandateLive(fetcher, mandateId, {
  fastMs = LIVE_FAST_MS,
  slowMs = LIVE_SLOW_MS,
  hiddenMs = LIVE_HIDDEN_MS,
  enabled = true,
} = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: false, reconnecting: false, updatedAt: null });
  const snapshot = useRef(null);
  const since = useRef(null);
  const timer = useRef(null);
  const controller = useRef(null);
  const attempts = useRef(0);
  const ticket = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const tickRef = useRef(() => {});
  const scheduleRef = useRef(() => {});

  const clearTimer = useCallback(() => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
  }, []);
  scheduleRef.current = (delay) => {
    clearTimer();
    timer.current = setTimeout(() => tickRef.current(), delay);
  };

  const tick = useCallback(async () => {
    if (!enabled || !mandateId) return;
    clearTimer();
    const mine = ++ticket.current;
    if (controller.current) controller.current.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    setState((s) => ({ ...s, loading: s.data === null }));
    try {
      const answer = await fetcherRef.current(since.current, ctl.signal);
      if (mine !== ticket.current || ctl.signal.aborted) return;
      if (answer && answer.version) since.current = answer.version;
      attempts.current = 0;
      const current = answer && answer.changed === false ? snapshot.current : answer;
      snapshot.current = current;
      setState({ data: current, error: null, reconnecting: false, loading: false, updatedAt: new Date() });
      const active = !!(current && (current.counts?.discovery_in_progress || current.status === "active"));
      scheduleRef.current(document.hidden ? hiddenMs : active ? fastMs : slowMs);
    } catch (e) {
      if (mine !== ticket.current || ctl.signal.aborted) return;
      attempts.current += 1;
      setState((s) => ({ ...s, error: describeApiError(e), reconnecting: true, loading: false }));
      scheduleRef.current(Math.min(hiddenMs, slowMs * 2 ** Math.min(attempts.current, 3)));
    }
  }, [enabled, mandateId, hiddenMs, fastMs, slowMs, clearTimer]);
  tickRef.current = tick;

  useEffect(() => {
    if (!enabled || !mandateId) return undefined;
    since.current = null;
    snapshot.current = null;
    attempts.current = 0;
    setState({ data: null, error: null, loading: true, reconnecting: false, updatedAt: null });
    tick();
    const onVisibility = () => { if (!document.hidden) tick(); };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      clearTimer();
      if (controller.current) controller.current.abort();
      ticket.current += 1; // a response already in flight belongs to an unmounted stream
    };
  }, [tick, enabled, mandateId, clearTimer]);

  const reload = useCallback(() => { since.current = null; ticket.current += 1; tick(); }, [tick]);
  return { ...state, reload };
}
