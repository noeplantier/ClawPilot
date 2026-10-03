import { niceScale, hasAnyValue, linePoints } from "@/lib/chartMath";

test("the scale starts at 0, uses integers and ends at or above the maximum", () => {
  for (const max of [0, 1, 3, 7, 10, 99, 1234]) {
    const { end, ticks } = niceScale(max);
    expect(ticks[0]).toBe(0);
    expect(end).toBeGreaterThanOrEqual(max);
    expect(ticks.every(Number.isInteger)).toBe(true);
    expect(ticks.length).toBeLessThanOrEqual(6);
  }
});

test("an all-zero or empty data set is detected so the page can say so instead of drawing nothing", () => {
  expect(hasAnyValue([], ["a"])).toBe(false);
  expect(hasAnyValue([{ a: 0, b: 0 }], ["a", "b"])).toBe(false);
  expect(hasAnyValue([{ a: 0, b: 2 }], ["a", "b"])).toBe(true);
});

test("a higher value is drawn higher and days go left to right", () => {
  const rows = [{ v: 0 }, { v: 5 }, { v: 2 }];
  const { x, y, points } = linePoints(rows, "v", 5);
  expect(x(0)).toBeLessThan(x(2));
  expect(y(5)).toBeLessThan(y(0));
  expect(points).toHaveLength(3);
});
