import { detectedSignals, resultSummary, unknownCount, validateDiscover } from "@/lib/sourcesForm";

const WORLD = { name: "world_fixture", kind: "local", verticals: ["restaurants", "hotels"], max_radius_m: 20000000 };
const OSM = { name: "openstreetmap", kind: "network", verticals: ["restaurants"], max_radius_m: 10000 };
const base = { vertical: "restaurants", limit: 25, country: "", city: "", lat: "", lon: "", radius_m: 5000 };

test("a local source needs no position and sends only what was filled", () => {
  const out = validateDiscover(WORLD, base);
  expect(out).toEqual({ ok: true, body: { provider: "world_fixture", vertical: "restaurants", limit: 25, radius_m: 5000 } });
});

test("a network source needs a position and a country, and says so", () => {
  const out = validateDiscover(OSM, base);
  expect(out.ok).toBe(false);
  expect(out.errors.lat).toMatch(/town|position/);
  expect(out.errors.country).toMatch(/required/);
});

test("rules mirror the API: coordinates together, ranges, radius cap, vertical coverage", () => {
  expect(validateDiscover(OSM, { ...base, lat: "45", country: "fr" }).errors.lat).toMatch(/together/);
  expect(validateDiscover(OSM, { ...base, lat: "95", lon: "4", country: "FR" }).ok).toBe(false);
  expect(validateDiscover(OSM, { ...base, lat: "45", lon: "4", country: "FR", radius_m: 20000 }).errors.radius_m).toMatch(/At most 10000/);
  expect(validateDiscover(OSM, { ...base, vertical: "hotels", lat: "45", lon: "4", country: "FR" }).errors.vertical).toMatch(/does not cover/);
  expect(validateDiscover(WORLD, { ...base, limit: 500 }).errors.limit).toMatch(/At most 100/);
});

test("a valid network request is normalised (upper-case country, numbers)", () => {
  const out = validateDiscover(OSM, { ...base, lat: "45.764", lon: "4.8357", country: "fr", radius_m: "3000" });
  expect(out.body).toMatchObject({ provider: "openstreetmap", lat: 45.764, lon: 4.8357, country: "FR", radius_m: 3000 });
});

test("the summary is exact and a zero is said plainly", () => {
  expect(resultSummary({ total: 0 })).toBe("No place found for these parameters.");
  expect(resultSummary({ total: 1, duplicates_merged: 0, truncated: false })).toBe("1 place.");
  expect(resultSummary({ total: 12, duplicates_merged: 2, truncated: true })).toContain("12 places, 2 duplicates merged.");
});

test("only detected signals are findings; unknown stays unknown", () => {
  const place = { signals: [{ key: "a", state: "detected" }, { key: "b", state: "unknown" }, { key: "c", state: "not_detected" }] };
  expect(detectedSignals(place).map((s) => s.key)).toEqual(["a"]);
  expect(unknownCount(place)).toBe(1);
});
