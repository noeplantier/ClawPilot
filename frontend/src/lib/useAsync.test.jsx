import { act } from "react";
import { createRoot } from "react-dom/client";

import { useAsync } from "@/lib/outreach";
import { useLive } from "@/lib/live";
import * as swr from "@/lib/swr";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
let last;
function Async({ fn, opts, dep = 0 }) {
  last = useAsync(fn, [dep], opts);
  return null;
}
function Live({ fn, opts }) {
  last = useLive(fn, [], opts);
  return null;
}

const setHidden = (hidden) => {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
};

beforeEach(() => { jest.useFakeTimers(); container = document.createElement("div"); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); setHidden(false); jest.useRealTimers(); });

test("without a key nothing is cached and the first state is loading, as before", async () => {
  let release;
  const fn = jest.fn(() => new Promise((r) => { release = r; }));
  await act(async () => root.render(<Async fn={fn} />));
  expect(last.loading).toBe(true);
  expect(last.data).toBeNull();
  await act(async () => release({ n: 1 }));
  expect(last.data).toEqual({ n: 1 });
  expect(last.loading).toBe(false);
  expect(swr.read("anything")).toBeNull();
});

test("with a key, the last answer is on screen at once while the server is asked again, then replaced", async () => {
  swr.write("page", { n: "old" });
  let release;
  const fn = jest.fn(() => new Promise((r) => { release = r; }));
  await act(async () => root.render(<Async fn={fn} opts={{ key: "page" }} />));
  expect(last.data).toEqual({ n: "old" }); // no blank screen, no spinner: the cached answer
  expect(last.loading).toBe(false);
  expect(fn).toHaveBeenCalledTimes(1); // and it is revalidated right away
  await act(async () => release({ n: "new" }));
  expect(last.data).toEqual({ n: "new" });
  expect(swr.read("page").data).toEqual({ n: "new" }); // the cache follows the server
});

test("a failing revalidation keeps the cached answer and says it is stale; with nothing cached it is an error", async () => {
  swr.write("page", { n: "old" });
  await act(async () => root.render(<Async fn={() => Promise.reject(new Error("offline"))} opts={{ key: "page" }} />));
  expect(last.data).toEqual({ n: "old" });
  expect(last.stale).toBe(true);
  expect(last.error).toBeNull();
  await act(async () => root.unmount());
  root = createRoot(container);
  await act(async () => root.render(<Async fn={() => Promise.reject(new Error("offline"))} opts={{ key: "other" }} />));
  expect(last.data).toBeNull();
  expect(last.error).toBeTruthy();
});

test("another query shows its own cached answer, never the previous query's", async () => {
  swr.write("q:1", "one");
  swr.write("q:2", "two");
  const fn = (n) => () => Promise.resolve(`fresh ${n}`);
  await act(async () => root.render(<Async fn={fn(1)} dep={1} opts={{ key: "q:1" }} />));
  expect(last.data).toBe("fresh 1");
  let release;
  const slow = () => new Promise((r) => { release = r; });
  await act(async () => root.render(<Async fn={slow} dep={2} opts={{ key: "q:2" }} />));
  expect(last.data).toBe("two"); // while q:2 is being fetched
  await act(async () => release("fresh 2"));
  expect(last.data).toBe("fresh 2");
});

test("with an interval it refreshes by itself while the tab is shown, pauses while hidden and catches up when shown again", async () => {
  const fn = jest.fn().mockResolvedValue({ n: 1 });
  await act(async () => root.render(<Async fn={fn} opts={{ intervalMs: 1000 }} />));
  expect(fn).toHaveBeenCalledTimes(1);
  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(fn).toHaveBeenCalledTimes(2);
  await act(async () => setHidden(true));
  await act(async () => { jest.advanceTimersByTime(3000); });
  expect(fn).toHaveBeenCalledTimes(2); // nothing is fetched for a tab nobody sees
  await act(async () => setHidden(false));
  expect(fn).toHaveBeenCalledTimes(3); // refreshed at once on return, not at the next tick
});

test("a refresh by timer never flashes the loading state, and a failing one keeps what is shown", async () => {
  const answers = [{ n: 1 }, new Error("offline")];
  const fn = jest.fn(() => { const a = answers.shift(); return a instanceof Error ? Promise.reject(a) : Promise.resolve(a); });
  await act(async () => root.render(<Async fn={fn} opts={{ intervalMs: 1000 }} />));
  await act(async () => { jest.advanceTimersByTime(1000); });
  expect(last.loading).toBe(false);
  expect(last.data).toEqual({ n: 1 });
  expect(last.stale).toBe(true);
  expect(last.error).toBeNull();
});

test("useLive also starts from the cached answer and refreshes when the tab is shown again", async () => {
  swr.write("live", [{ id: 1 }]);
  const fn = jest.fn().mockResolvedValue([{ id: 1 }, { id: 2 }]);
  await act(async () => root.render(<Live fn={fn} opts={{ key: "live", intervalMs: 60000 }} />));
  expect(last.data).toHaveLength(2);
  expect(swr.read("live").data).toHaveLength(2);
  await act(async () => setHidden(true));
  await act(async () => setHidden(false));
  expect(fn).toHaveBeenCalledTimes(2);
});
