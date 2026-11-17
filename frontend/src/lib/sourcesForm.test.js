import { RADII, defaultProvider, detectedSignals, isGem, opportunityOf, radiiFor, resultSummary, unknownCount, validateDiscover, zoneLine } from "@/lib/sourcesForm";

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

describe("an automatic zone and justified opportunities", () => {
  it("offers only the radii the source accepts", () => {
    expect(radiiFor({ max_radius_m: 5000 })).toEqual([1000, 3000, 5000]);
    expect(radiiFor({ max_radius_m: 50000 })).toEqual(RADII);
  });
  it("opens the first real source available, else the demo", () => {
    const demo = { name: "world_fixture", kind: "local", available: true };
    const osm = { name: "openstreetmap", kind: "network", available: true };
    expect(defaultProvider([demo, osm]).name).toBe("openstreetmap");
    expect(defaultProvider([demo, { ...osm, available: false }]).name).toBe("world_fixture");
    expect(defaultProvider([])).toBeNull();
  });
  it("says the zone in words", () => {
    expect(zoneLine({ city: "Lyon", lat: "45.76", lon: "4.83", radius_m: 3000 })).toBe("Lyon · rayon 3 km");
    expect(zoneLine({ city: "", lat: "45.76", lon: "4.83", radius_m: 500 })).toBe("45.7600, 4.8300 · rayon 500 m");
    expect(zoneLine({ city: "", lat: "", lon: "", radius_m: 3000 })).toBe("");
  });
  it("an opportunity is a detected gap with its evidence and source, never an unknown", () => {
    const place = { source_name: "openstreetmap", signals: [
      { key: "no_website", state: "detected", evidence: "No website listed in openstreetmap" },
      { key: "incomplete_listing", state: "unknown", evidence: "?" },
      { key: "public_contact_present", state: "detected", evidence: "phone" },
    ] };
    expect(opportunityOf(place)).toEqual([{ key: "no_website", label: "Aucun site propre déclaré par la source", evidence: "No website listed in openstreetmap", source: "openstreetmap" }]);
    expect(isGem(place)).toBe(true);
    expect(isGem({ source_name: "x", signals: [{ key: "no_website", state: "unknown", evidence: "" }] })).toBe(false);
  });
});
