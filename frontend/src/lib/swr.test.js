/* global Storage */
import { clear, read, write } from "@/lib/swr";

beforeEach(() => { clear(); window.sessionStorage.clear(); });

test("what was written is read back, from memory and from the session after a reload", () => {
  write("leads", [{ id: 1 }]);
  expect(read("leads").data).toEqual([{ id: 1 }]);
  expect(typeof read("leads").at).toBe("number");
  // a reload empties memory but not the session
  const raw = window.sessionStorage.getItem("outreachos.swr.v1:leads");
  clear();
  window.sessionStorage.setItem("outreachos.swr.v1:leads", raw);
  expect(read("leads").data).toEqual([{ id: 1 }]);
});

test("an unknown key, no key, a corrupt entry and an undefined answer give nothing", () => {
  expect(read("nope")).toBeNull();
  expect(read(null)).toBeNull();
  window.sessionStorage.setItem("outreachos.swr.v1:bad", "{not json");
  expect(read("bad")).toBeNull();
  window.sessionStorage.setItem("outreachos.swr.v1:shape", JSON.stringify({ hello: 1 }));
  expect(read("shape")).toBeNull();
  write("undef", undefined);
  expect(read("undef")).toBeNull();
});

test("an answer too big for the session stays in memory only, and sign-out clears everything", () => {
  const big = "x".repeat(450000);
  write("big", big);
  expect(read("big").data).toBe(big);
  expect(window.sessionStorage.getItem("outreachos.swr.v1:big")).toBeNull();
  write("small", 1);
  clear();
  expect(read("small")).toBeNull();
  expect(read("big")).toBeNull();
  expect(Object.keys(window.sessionStorage)).toEqual([]);
});

test("blocked storage does not break the cache: it falls back to memory", () => {
  const spy = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  write("k", { a: 1 });
  expect(read("k").data).toEqual({ a: 1 });
  spy.mockRestore();
});
