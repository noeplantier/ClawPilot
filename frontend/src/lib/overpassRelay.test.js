import { acceptableQuery, originAllowed, RELAY_MIRRORS, MAX_QUERY_CHARS } from "@/lib/overpassRelay";

const REAL = '[out:json][timeout:25];\n(\n  nwr["amenity"~"restaurant"]["name"](45.7,4.8,45.8,4.9);\n);\nout center meta 600;';

test("only the JSON queries of this application are relayed", () => {
  expect(acceptableQuery(REAL)).toBe(true);
  expect(acceptableQuery("[out:json];node(1);out;")).toBe(true);
  for (const bad of ["", "   ", null, undefined, 42, "node(1);out;", "[out:xml];node(1);out;", "[out:csv(name)];node(1);out;",
    "[out:json][timeout:600];node(1);out;", `[out:json];${"x".repeat(MAX_QUERY_CHARS)}`, "[out:json];node(1);[out:xml];"]) {
    expect(acceptableQuery(bad)).toBe(false);
  }
});

test("a page of another site may not use the relay, a request without Origin (the API) may", () => {
  expect(originAllowed("https://plantiers-outreach-os.netlify.app", "plantiers-outreach-os.netlify.app")).toBe(true);
  expect(originAllowed("https://evil.example", "plantiers-outreach-os.netlify.app")).toBe(false);
  expect(originAllowed("not a url", "plantiers-outreach-os.netlify.app")).toBe(false);
  expect(originAllowed(null, "plantiers-outreach-os.netlify.app")).toBe(true);
});

test("the relay only ever forwards to public Overpass servers over https", () => {
  expect(RELAY_MIRRORS.length).toBeGreaterThanOrEqual(3);
  RELAY_MIRRORS.forEach((u) => { expect(u.startsWith("https://")).toBe(true); expect(u.endsWith("/interpreter")).toBe(true); });
});
