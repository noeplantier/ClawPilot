import { areaTooLarge, importRows, summarize, summaryText, markerColor, panelPadding, reachablePlace, isHot, readyOnly, readySummary } from "@/lib/mapSearch";

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
  it("keeps a popup clear of the search card on the left and the results drawer on the right", () => {
    expect(panelPadding({ narrow: false, searchOpen: true, panelOpen: true, hidden: false })).toEqual({ topLeft: [440, 70], bottomRight: [400, 50] });
  });
  it("frees the room of a panel that is minimised or closed, and of every panel when they are hidden", () => {
    expect(panelPadding({ narrow: false, searchOpen: false, panelOpen: false, hidden: false })).toEqual({ topLeft: [20, 70], bottomRight: [20, 50] });
    expect(panelPadding({ narrow: false, searchOpen: true, panelOpen: true, hidden: true })).toEqual({ topLeft: [20, 70], bottomRight: [20, 50] });
  });
  it("on a phone the panels are above and below the map, not beside it", () => {
    expect(panelPadding({ narrow: true, searchOpen: true, panelOpen: true, hidden: false })).toEqual({ topLeft: [20, 360], bottomRight: [20, 280] });
  });
});

test("a place found by the search is drawn only when it published both a phone and an e-mail", () => {
  expect(reachablePlace({ phone: "+33 4 78 12 34 56", email: "contact@chez-marcel.example" })).toBe(true);
  expect(reachablePlace({ phone: "+33 4 78 12 34 56", email: null })).toBe(false); // unknown is not a value
  expect(reachablePlace({ phone: "", email: "a@b.example" })).toBe(false);
  expect(reachablePlace(null)).toBe(false);
});
