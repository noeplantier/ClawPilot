// The town search's pure logic: URLs, parsing of the two public services, matching, ranking, and the counts shown next to a town.
// The answers below are recorded in the documented shape of geo.api.gouv.fr and api-adresse.data.gouv.fr: no network here.
import {
  addressUrl, centroids, communesUrl, countsText, expandSaint, fold, forms, hottest, isPostcode, matchClass, parseAddress, parseCommunes, suggest, zoomFor,
} from "@/lib/cityComplete";

const commune = (nom, code, codes, lon, lat, population, dep) => ({ nom, code, codesPostaux: codes, centre: { type: "Point", coordinates: [lon, lat] }, population, departement: dep });
const COMMUNES = [
  commune("Lyon", "69123", ["69001", "69002", "69003"], 4.832, 45.758, 522250, { code: "69", nom: "Rhône" }),
  commune("Lyons-la-Forêt", "27375", ["27480"], 1.476, 49.399, 700, { code: "27", nom: "Eure" }),
  commune("Saint-Étienne", "42218", ["42000", "42100"], 4.387, 45.434, 173000, { code: "42", nom: "Loire" }),
  commune("Saint-Denis", "93066", ["93200"], 2.357, 48.936, 113000, { code: "93", nom: "Seine-Saint-Denis" }),
  commune("Saint-Denis", "97411", ["97400"], 55.46, -20.88, 150000, { code: "974", nom: "La Réunion" }),
];
const STATS = [
  { city: "Lyon", key: "lyon", hot: 12, warm: 9, cold: 19, total: 40 },
  { city: "Saint-Étienne", key: "saint etienne", hot: 2, warm: 1, cold: 0, total: 3 },
  { city: "Villeurbanne", key: "villeurbanne", hot: 0, warm: 1, cold: 4, total: 5 },
];

describe("fold (the same key as the server)", () => {
  it("makes one key of the spellings of one town", () => {
    for (const w of ["Saint-Étienne", "saint etienne", "SAINT ETIENNE", "St-Etienne", " st  étienne ", "Saint’Étienne"]) expect(fold(w)).toBe("saint etienne");
    expect(fold("Strasbourg")).toBe("strasbourg");
    expect(fold("Ste-Foy-lès-Lyon")).toBe("sainte foy les lyon");
    expect(fold(null)).toBe("");
  });
});

describe("urls", () => {
  it("asks the communes API by name, boosted by population, with the fields the page uses", () => {
    const url = communesUrl("Lyon");
    expect(url.startsWith("https://geo.api.gouv.fr/communes?nom=Lyon&")).toBe(true);
    expect(url).toContain("boost=population");
    expect(url).toContain("limit=8");
    expect(url).toContain("fields=nom,code,codesPostaux,centre,population,departement");
  });
  it("asks by postcode when five digits are typed, and only then", () => {
    expect(isPostcode("69002")).toBe(true);
    expect(isPostcode("6900")).toBe(false);
    expect(communesUrl("69002")).toContain("codePostal=69002");
    expect(communesUrl("69002")).not.toContain("nom=");
    expect(communesUrl("690")).toContain("nom=690");
  });
  it("writes St and Ste out in full when the word is finished, and escapes the rest", () => {
    expect(expandSaint("st etienne")).toBe("saint etienne");
    expect(expandSaint("Ste-Foy")).toBe("sainte-Foy");
    expect(expandSaint("st")).toBe("st"); // still being typed: it may become Strasbourg
    expect(expandSaint("Stains")).toBe("Stains");
    expect(communesUrl("l'isle & co")).toContain("nom=l'isle%20%26%20co");
    expect(addressUrl("st-denis")).toContain("q=saint-denis");
  });
});

describe("parsing the public services", () => {
  it("reads communes: the centre is [lon, lat], one postcode is shown, several give a range", () => {
    const [lyon, forest] = parseCommunes(COMMUNES);
    expect(lyon).toMatchObject({ name: "Lyon", lat: 45.758, lon: 4.832, population: 522250, label: "Lyon (69)", detail: "Rhône · 69001–69003" });
    expect(forest.label).toBe("Lyons-la-Forêt (27480)");
  });
  it("drops what has no position and never invents one", () => {
    expect(parseCommunes([{ nom: "Nulle part", code: "1" }, { nom: "X", centre: { coordinates: ["a", "b"] } }, null])).toEqual([]);
    expect(parseCommunes({ message: "error" })).toEqual([]);
    expect(parseCommunes(null)).toEqual([]);
  });
  it("reads the address API's municipalities as the fallback", () => {
    const out = parseAddress({ features: [{ geometry: { coordinates: [4.83, 45.76] }, properties: { city: "Lyon", postcode: "69001", citycode: "69123", context: "69, Rhône, Auvergne-Rhône-Alpes" } }, { properties: { city: "Sans position" } }] });
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ name: "Lyon", label: "Lyon (69001)", lat: 45.76, lon: 4.83, detail: "69, Rhône, Auvergne-Rhône-Alpes" });
    expect(parseAddress({})).toEqual([]);
  });
});

describe("matching", () => {
  it("ranks the whole name, then the start of a name or of one of its words, then the inside", () => {
    expect(matchClass("lyon", "Lyon")).toBe(0);
    expect(matchClass("lyo", "Lyon")).toBe(1);
    expect(matchClass("etienne", "Saint-Étienne")).toBe(1);
    expect(matchClass("tienne", "Saint-Étienne")).toBe(2);
    expect(matchClass("paris", "Lyon")).toBeNull();
  });
  it("ignores accents, case and hyphens in what is typed", () => {
    expect(matchClass("SAINT etienne", "Saint-Étienne")).toBe(0);
    expect(matchClass("st-etienne", "Saint-Étienne")).toBe(0);
  });
  it("keeps both readings of a last word still being typed: `st` may be Saint or Strasbourg", () => {
    expect(forms("st")).toEqual(["st", "saint"]);
    expect(forms("st etienne")).toEqual(["saint etienne"]);
    expect(matchClass("st", "Strasbourg")).toBe(1);
    expect(matchClass("st", "Saint-Étienne")).toBe(1);
    expect(matchClass("ste", "Sète")).toBeNull(); // not a prefix of Sète once accents go: "sete"
    expect(matchClass("sa", "Saint-Étienne")).toBe(1);
  });
});

describe("suggest", () => {
  // what the communes API answers for each text: only communes whose name matches, most populous first
  const answer = (...names) => parseCommunes(COMMUNES.filter((c) => names.includes(c.nom)));
  const remote = answer("Lyon", "Lyons-la-Forêt", "Saint-Étienne", "Saint-Denis");
  const base = { remote: answer("Lyon", "Lyons-la-Forêt"), remoteFor: "ly", stats: STATS };

  it("says nothing under two characters", () => {
    expect(suggest("l", base)).toEqual([]);
    expect(suggest("", base)).toEqual([]);
  });
  it("attaches the counted leads of each town, hot first in the figures", () => {
    const out = suggest("ly", base);
    expect(out.map((e) => e.name)).toEqual(["Lyon", "Lyons-la-Forêt"]);
    expect(out[0].counts).toEqual({ hot: 12, warm: 9, cold: 19, total: 40 });
    expect(out.find((e) => e.name === "Lyons-la-Forêt").counts).toEqual({ hot: 0, warm: 0, cold: 0, total: 0 });
  });
  it("puts a town with hot leads above an equally good match without any", () => {
    const saint = answer("Saint-Denis", "Saint-Étienne");
    const out = suggest("saint", { remote: saint, remoteFor: "saint", stats: STATS });
    expect(out.map((e) => e.name)).toEqual(["Saint-Étienne", "Saint-Denis", "Saint-Denis"]);
    expect(out[0].counts.hot).toBe(2);
  });
  it("gives the leads of a name to its most populous commune only", () => {
    const out = suggest("saint", { remote: answer("Saint-Denis"), remoteFor: "saint", stats: [{ city: "Saint-Denis", key: "saint denis", hot: 3, warm: 0, cold: 1, total: 4 }] });
    const denis = out.filter((e) => e.name === "Saint-Denis");
    expect(denis.map((e) => e.counts)).toEqual([{ hot: 3, warm: 0, cold: 1, total: 4 }, null]);
    expect(denis[0].detail).toContain("Seine-Saint-Denis"); // the first of the API's answer (ranked by population)
  });
  it("shows no count at all while the counts are not loaded (never a made-up 0)", () => {
    const out = suggest("ly", { remote, remoteFor: "ly", stats: null });
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((e) => e.counts === null)).toBe(true);
  });
  it("narrows an answer meant for a shorter text instead of showing what no longer matches", () => {
    const stale = suggest("lyon", { remote: answer("Lyon", "Lyons-la-Forêt", "Saint-Étienne"), remoteFor: "ly", stats: STATS });
    expect(stale.map((e) => e.name)).toEqual(["Lyon", "Lyons-la-Forêt"]);
    const fresh = suggest("lyon", { remote: parseCommunes([commune("Lyon", "69123", ["69001"], 4.8, 45.7, 5, { code: "69" }), commune("Lion-sur-Mer", "1", ["14780"], 0, 49, 3, { code: "14" })]), remoteFor: "lyon", stats: null });
    expect(fresh.map((e) => e.name)).toEqual(["Lyon", "Lion-sur-Mer"]); // the service's own fuzzy match is kept when it is current
  });
  it("still offers a town of the leads that the commune list did not return, with its position when known", () => {
    const positions = centroids([{ city: "Villeurbanne", lat: 45.77, lon: 4.88 }, { city: "villeurbanne ", lat: 45.75, lon: 4.9 }]);
    const out = suggest("villeur", { remote: [], remoteFor: "villeur", stats: STATS, positions });
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ name: "Villeurbanne", local: true, counts: { hot: 0, warm: 1, cold: 4, total: 5 } });
    expect(out[0].lat).toBeCloseTo(45.76);
    expect(out[0].lon).toBeCloseTo(4.89);
    expect(suggest("villeur", { remote: [], remoteFor: "villeur", stats: STATS })[0].lat).toBeNull(); // unknown, not 0
  });
  it("does not offer a town twice when the API returned it", () => {
    const out = suggest("lyon", { remote: answer("Lyon", "Lyons-la-Forêt"), remoteFor: "lyon", stats: STATS });
    expect(out.filter((e) => e.name === "Lyon")).toHaveLength(1);
  });
  it("cuts the list to the limit", () => {
    expect(suggest("saint", { remote: answer("Saint-Denis", "Saint-Étienne"), remoteFor: "saint", stats: STATS, limit: 2 })).toHaveLength(2);
  });
});

describe("what is shown before anything is typed", () => {
  it("lists the towns that hold leads, hottest first as the server sorted them, and nothing when none do", () => {
    expect(hottest(STATS, 2).map((e) => e.name)).toEqual(["Lyon", "Saint-Étienne"]);
    expect(hottest([{ city: "Vide", key: "vide", hot: 0, warm: 0, cold: 0, total: 0 }])).toEqual([]);
    expect(hottest(null)).toEqual([]);
  });
  it("carries the position of my prospects there, and none when unknown (never 0)", () => {
    const out = hottest(STATS, 3, centroids([{ city: "Lyon", lat: 45.76, lon: 4.84 }]));
    expect(out[0]).toMatchObject({ name: "Lyon", lat: 45.76, lon: 4.84 });
    expect(out[1]).toMatchObject({ name: "Saint-Étienne", lat: null, lon: null });
  });
  it("writes the counts plainly, and nothing when they are unknown", () => {
    expect(countsText({ hot: 12, warm: 9, cold: 19, total: 40 })).toBe("12 hot · 40 leads");
    expect(countsText({ hot: 0, warm: 0, cold: 1, total: 1 })).toBe("0 hot · 1 lead");
    expect(countsText({ hot: 0, warm: 0, cold: 0, total: 0 })).toBe("no lead yet");
    expect(countsText(null)).toBeNull();
  });
});

describe("zoom", () => {
  it("flies closer to a village than to a city, and to the usual level when the size is unknown", () => {
    expect(zoomFor(700)).toBe(15);
    expect(zoomFor(522250)).toBe(14);
    expect(zoomFor(null)).toBe(14);
  });
});
