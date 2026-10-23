/* global Storage */
import { isTypingTarget, readPref, writePref } from "@/lib/uiPrefs";

beforeEach(() => window.localStorage.clear());

test("a saved preference comes back, a missing one gives the fallback", () => {
  expect(readPref("sidebar", false)).toBe(false);
  writePref("sidebar", true);
  expect(readPref("sidebar", false)).toBe(true);
  writePref("map", { search: false });
  expect(readPref("map", {})).toEqual({ search: false });
});

test("broken storage never breaks the page", () => {
  window.localStorage.setItem("pos.ui.bad", "{not json");
  expect(readPref("bad", "fallback")).toBe("fallback");
  const spy = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(() => writePref("x", 1)).not.toThrow();
  spy.mockRestore();
  const get = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(readPref("x", 7)).toBe(7);
  get.mockRestore();
});

test("shortcuts ignore typing in fields", () => {
  expect(isTypingTarget(document.createElement("input"))).toBe(true);
  expect(isTypingTarget(document.createElement("select"))).toBe(true);
  expect(isTypingTarget(document.createElement("div"))).toBe(false);
  expect(isTypingTarget(null)).toBe(false);
});
