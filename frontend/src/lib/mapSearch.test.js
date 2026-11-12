import { areaTooLarge, importRows, summarize, summaryText, markerColor, panelPadding, reachablePlace, isHot, readyOnly, readySummary, zoneOf, zoneSummary, journeyLink } from "@/lib/mapSearch";

const A = { external_id: "node/1", name: "A", lat: 45.7, lon: 4.8, email: "a@a.fr", phone: "+33 1", website: "https://a.fr", source_url: "u" };
const B = { external_id: "node/2", name: "B", lat: 45.7, lon: 4.8, email: null, phone: "+33 2", website: null, source_url: "u" };
const C = { external_id: "node/3", name: "C", lat: 45.7, lon: 4.8, email: null, phone: null, website: null, source_url: "u" };

test("the area limits mirror the API", () => {
  expect(areaTooLarge({ south: 45.75, north: 45.77, west: 4.8, east: 4.85 })).toBe(false);
  expect(areaTooLarge({ south: 45.0, north: 45.5, west: 4.8, east: 4.85 })).toBe(true);
  expect(areaTooLarge({ south: 45.75, north: 45.77, west: 4.0, east: 4.5 })).toBe(true);
});

test("counts are exact and a missing value is not invented", () => {
  expect(summarize([A, B, C])).toEqual({ total: 3, email: 1, phone: 2, website: 1 });
  expect(summaryText([A, B, C], false)).toBe("3 places: 1 with a published e-mail, 2 with a phone, 1 with a website.");
  expect(summaryText([], false)).toBe("No named place with published data in this area.");
  expect(summaryText([A], true)).toContain("zoom in");
});

test("import rows carry only what was published, and the position", () => {
  const [row] = importRows([B]);
  expect(row).toMatchObject({ name: "B", phone: "+33 2", email: null, lat: 45.7, lon: 4.8, external_id: "node/2" });
  expect(Object.keys(row)).not.toContain("score");
});

test("marker colours tell what is reachable", () => {
  expect(markerColor(A)).toBe("#15803D");
  expect(markerColor(B)).toBe("#B45309");
  expect(markerColor(C)).toBe("#6B6B66");
});

test("only the prospects the server qualified are drawn, and the summary counts them exactly, hot apart", () => {
  const mine = [
    { id: "1", map_ready: true, has_website: true, priority: "hot" },
    { id: "2", map_ready: true, has_website: false, priority: "qualified" },
    { id: "3", map_ready: false, has_website: true }, // an e-mail, a phone, an address or a position is missing: the server decided
    { id: "4" }, // an older answer without the flag is never guessed qualified
  ];
  expect(readyOnly(mine).map((p) => p.id)).toEqual(["1", "2"]);
  expect(isHot(mine[0])).toBe(true);
  expect(isHot(mine[1])).toBe(false); // qualified is not hot: only an observed, sourced intent makes a prospect hot
  expect(readySummary(mine)).toBe("2 qualified prospects with e-mail, phone and address, 1 with a website, 1 hot (observed intent).");
  expect(readySummary([mine[1]])).toBe("1 qualified prospect with e-mail, phone and address, 0 with a website, none hot: no commercial intent observed.");
  expect(readySummary([mine[2], mine[3]])).toBe("No qualified prospect on the map yet: the incomplete ones wait in Leads, to enrich.");
  expect(readySummary([])).toBe("No qualified prospect on the map yet: the incomplete ones wait in Leads, to enrich.");
});

describe("panelPadding", () => {
  it("keeps a popup clear of the one Prospection panel on the left, and leaves the right of the map free", () => {
    expect(panelPadding({ narrow: false, open: true, hidden: false })).toEqual({ topLeft: [440, 70], bottomRight: [20, 50] });
  });
  it("frees the room of the panel when it is minimised, and of every panel when they are hidden", () => {
    expect(panelPadding({ narrow: false, open: false, hidden: false })).toEqual({ topLeft: [20, 70], bottomRight: [20, 50] });
    expect(panelPadding({ narrow: false, open: true, hidden: true })).toEqual({ topLeft: [20, 70], bottomRight: [20, 50] });
  });
  it("on a phone the panel is above the map, not beside it", () => {
    expect(panelPadding({ narrow: true, open: true, hidden: false })).toEqual({ topLeft: [20, 360], bottomRight: [20, 50] });
  });
});

const BOX = { status: "succeeded", south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant" };

describe("the zone a search really looked at", () => {
  it("is the box and the category of a succeeded search, and nothing before that", () => {
    expect(zoneOf(BOX)).toEqual({ south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant" });
    expect(zoneOf(null)).toBeNull();
    expect(zoneOf({ ...BOX, status: "running" })).toBeNull();
    expect(zoneOf({ ...BOX, status: "failed" })).toBeNull();
    expect(zoneOf({ ...BOX, south: undefined })).toBeNull();
    expect(zoneOf({ ...BOX, category: "" })).toBeNull();
  });
  it("is described with its real coordinates and size, never an estimate of how many places it holds", () => {
    const text = zoneSummary(zoneOf(BOX));
    expect(text).toContain("45.700–45.800° N");
    expect(text).toContain("4.780–4.900° E");
    expect(text).toContain("≈ 9 × 11 km");
    expect(text).toContain("restaurant");
    expect(text).not.toMatch(/\d+ (établissements|places|prospects)/);
    expect(zoneSummary(null)).toBe("");
  });
  it("travels to the campaign in the address, the label only when there is one", () => {
    const link = journeyLink(zoneOf(BOX));
    expect(link.startsWith("/app/journey?")).toBe(true);
    const q = new URLSearchParams(link.split("?")[1]);
    expect([q.get("south"), q.get("west"), q.get("north"), q.get("east"), q.get("category")]).toEqual(["45.7", "4.78", "45.8", "4.9", "restaurant"]);
    expect(q.has("label")).toBe(false);
    expect(new URLSearchParams(journeyLink(zoneOf(BOX), "Lyon 6").split("?")[1]).get("label")).toBe("Lyon 6");
  });
});
