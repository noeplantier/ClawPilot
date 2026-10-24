import { EMPTY_FILTER, applyFilter, clusterPoints, facets, filterSummary, hasFilter, newIds } from "@/lib/mapCluster";

const P = (id, lat, lon, extra = {}) => ({ id, lat, lon, name: id, review_status: "pending", vertical: "restaurant", score: null, signals: [], ...extra });

test("close points merge into one cluster at a low zoom and separate when zoomed in", () => {
  const pts = [P("a", 45.764, 4.835), P("b", 45.765, 4.836), P("c", 48.85, 2.35)];
  const far = clusterPoints(pts, 5);
  expect(far.map((c) => c.count).sort()).toEqual([1, 2]);
  const near = clusterPoints(pts, 18);
  expect(near).toHaveLength(3);
  const merged = far.find((c) => c.count === 2);
  expect(merged.members.map((m) => m.id).sort()).toEqual(["a", "b"]);
  expect(merged.lat).toBeCloseTo(45.7645, 4);
});

test("identical coordinates stay one cluster at any zoom (no point is lost)", () => {
  const pts = [P("a", 10, 10), P("b", 10, 10)];
  expect(clusterPoints(pts, 19)).toEqual([expect.objectContaining({ count: 2 })]);
  expect(clusterPoints([], 3)).toEqual([]);
});

test("an unscored prospect never passes a score threshold", () => {
  const pts = [P("a", 0, 0, { score: 70 }), P("b", 0, 0, { score: 0 }), P("c", 0, 0)];
  expect(applyFilter(pts, { ...EMPTY_FILTER, minScore: "50" }).map((p) => p.id)).toEqual(["a"]);
  expect(applyFilter(pts, { ...EMPTY_FILTER, minScore: "0" }).map((p) => p.id)).toEqual(["a", "b"]); // 0 is a real score, null is not
  expect(applyFilter(pts, EMPTY_FILTER)).toHaveLength(3);
});

test("filters combine on vertical, status and detected signal", () => {
  const pts = [
    P("a", 0, 0, { vertical: "bakery", signals: ["no_website"] }),
    P("b", 0, 0, { vertical: "bakery", review_status: "approved", signals: ["no_website", "outdated_technology"] }),
    P("c", 0, 0, { vertical: "hotel" }),
  ];
  expect(applyFilter(pts, { ...EMPTY_FILTER, vertical: "bakery", signal: "no_website" })).toHaveLength(2);
  expect(applyFilter(pts, { ...EMPTY_FILTER, vertical: "bakery", status: "approved" }).map((p) => p.id)).toEqual(["b"]);
  expect(hasFilter(EMPTY_FILTER)).toBe(false);
  expect(hasFilter({ ...EMPTY_FILTER, minScore: "0" })).toBe(true);
});

test("facets are counted from the data and an empty set says so", () => {
  const pts = [P("a", 0, 0, { signals: ["x", "y"] }), P("b", 0, 0, { signals: ["x"], vertical: null })];
  expect(facets(pts)).toEqual({ verticals: [{ value: "restaurant", count: 1 }], signals: [{ value: "x", count: 2 }, { value: "y", count: 1 }] });
  expect(filterSummary(0, 0)).toBe("No prospect with a position yet.");
  expect(filterSummary(2, 5)).toBe("2 of 5 prospects match the filters.");
  expect(filterSummary(1, 1)).toBe("1 prospect on the map.");
});

test("newIds flags only what appeared since the previous poll, and nothing on the first load", () => {
  const a = P("a", 0, 0);
  const b = P("b", 0, 0);
  expect(newIds(null, [a, b]).size).toBe(0);
  expect([...newIds([a], [a, b])]).toEqual(["b"]);
});
