import { act } from "react";
import { createRoot } from "react-dom/client";

import { freshIds, useLive, useMandateLive } from "@/lib/live";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("freshIds names only what appeared, and nothing on the first load", () => {
  const id = (x) => x.id;
  expect(freshIds(null, [{ id: 1 }], id).size).toBe(0);
  expect([...freshIds([{ id: 1 }], [{ id: 1 }, { id: 2 }], id)]).toEqual([2]);
  expect(freshIds([{ id: 1 }, { id: 2 }], [{ id: 2 }], id).size).toBe(0); // a row that left is not "new"
});

let container;
let root;
let last;
function Probe({ fn, ms }) {
  last = useLive(fn, [], { intervalMs: ms });
  return null;
}

beforeEach(() => { jest.useFakeTimers(); container = document.createElement("div"); root = createRoot(container); });
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  jest.useRealTimers();
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
});

test("it refreshes on its own, flags new rows, and keeps the last data when a refresh fails", async () => {
  const answers = [[{ id: 1 }], [{ id: 1 }, { id: 2 }], new Error("offline"), [{ id: 1 }, { id: 2 }, { id: 3 }]];
  const fn = jest.fn(() => { const a = answers.shift(); return a instanceof Error ? Promise.reject(a) : Promise.resolve(a); });
  await act(async () => root.render(<Probe fn={fn} ms={1000} />));
  expect(last.data).toEqual([{ id: 1 }]);
  expect(last.fresh.size).toBe(0);
  expect(last.updatedAt).toBeInstanceOf(Date);

  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(last.data).toHaveLength(2);
  expect([...last.fresh]).toEqual([2]);

  await act(async () => { jest.advanceTimersByTime(1000); }); // the network drops
  expect(last.data).toHaveLength(2); // what is on screen stays
  expect(last.stale).toBe(true);
  expect(last.error).toBeNull();

  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(last.data).toHaveLength(3);
  expect(last.stale).toBe(false);
  expect([...last.fresh]).toEqual([3]);
});

test("only a failing first load is an error", async () => {
  await act(async () => root.render(<Probe fn={() => Promise.reject(new Error("boom"))} ms={1000} />));
  expect(last.data).toBeNull();
  expect(typeof last.error).toBe("string");
  expect(last.loading).toBe(false);
});

test("a hidden tab does not poll", async () => {
  const fn = jest.fn(() => Promise.resolve([{ id: 1 }]));
  Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
  await act(async () => root.render(<Probe fn={fn} ms={1000} />));
  expect(fn).toHaveBeenCalledTimes(1); // the first load only
  await act(async () => { jest.advanceTimersByTime(3000); });
  expect(fn).toHaveBeenCalledTimes(1);
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(fn).toHaveBeenCalledTimes(2);
});

let lastLive;
function MandateProbe({ fetcher, id = "m1" }) {
  lastLive = useMandateLive(fetcher, id, { fastMs: 1000, slowMs: 4000, hiddenMs: 8000 });
  return null;
}

test("the mandate stream sends its version, keeps unchanged data and updates incrementally", async () => {
  const fetcher = jest.fn()
    .mockResolvedValueOnce({ version: "v1", changed: true, status: "active", counts: { discovery_in_progress: true, hot_leads: 2 } })
    .mockResolvedValueOnce({ version: "v1", changed: false })
    .mockResolvedValue({ version: "v2", changed: true, status: "active", counts: { discovery_in_progress: false, hot_leads: 3 } });
  await act(async () => root.render(<MandateProbe fetcher={fetcher} />));
  expect(lastLive.data.counts.hot_leads).toBe(2);

  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(fetcher.mock.calls[1][0]).toBe("v1"); // incremental request
  expect(lastLive.data.counts.hot_leads).toBe(2); // no full reload on "unchanged"

  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(lastLive.data.counts.hot_leads).toBe(3);
});

test("a new tick aborts the previous in-flight mandate request", async () => {
  let firstSignal;
  const fetcher = jest.fn((since, signal) => {
    if (!firstSignal) { firstSignal = signal; return new Promise(() => {}); }
    return Promise.resolve({ version: "v1", changed: true, status: "paused" });
  });
  await act(async () => root.render(<MandateProbe fetcher={fetcher} />));
  expect(firstSignal.aborted).toBe(false);
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(firstSignal.aborted).toBe(true);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

test("a failed refresh keeps the snapshot, reconnects with backoff and cleans up on unmount", async () => {
  const fetcher = jest.fn()
    .mockResolvedValueOnce({ version: "v1", changed: true, status: "active", counts: { hot_leads: 1 } })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ version: "v2", changed: true, status: "active", counts: { hot_leads: 2 } });
  await act(async () => root.render(<MandateProbe fetcher={fetcher} />));
  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(lastLive.reconnecting).toBe(true);
  expect(lastLive.data.counts.hot_leads).toBe(1);

  await act(async () => { jest.advanceTimersByTime(8000); }); // capped backoff after one failure
  expect(lastLive.reconnecting).toBe(false);
  expect(lastLive.data.counts.hot_leads).toBe(2);

  const calls = fetcher.mock.calls.length;
  await act(async () => root.unmount());
  root = null;
  await act(async () => { jest.advanceTimersByTime(20000); });
  expect(fetcher).toHaveBeenCalledTimes(calls);
});
