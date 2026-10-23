import { act } from "react";
import { createRoot } from "react-dom/client";

import { freshIds, useLive } from "@/lib/live";

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
afterEach(async () => { await act(async () => root.unmount()); jest.useRealTimers(); });

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
