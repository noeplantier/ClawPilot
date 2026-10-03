import { areaTooLarge, importRows, summarize, summaryText, markerColor } from "@/lib/mapSearch";

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
