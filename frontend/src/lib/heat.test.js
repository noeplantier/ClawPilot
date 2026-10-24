import { EMPTY_RULE, LANES, LANE_LABEL, emptyNote, hasContact, heatTitle, inLane, isEmpty, laneCounts, splitEmpty } from "@/lib/heat";

const H = (tier, value, known, scored = true, score = 70) => ({ tier, value, info_pct: 50, known, missing: ["website", "city", "company", "vertical", "country", "title", "email", "phone"].filter((f) => !known.includes(f)), scored, score: scored ? score : null });

test("the title says what the heat is made of and what is missing, with no invented figure", () => {
  const t = heatTitle(H("hot", 72, ["email", "phone", "website", "city"]));
  expect(t).toContain("Hot · heat 72/100");
  expect(t).toContain("score 70 and 4 of 8 real fields known");
  expect(t).toContain("Known: e-mail, phone, website, city.");
  expect(t).toContain("Missing: company, category, country, job title.");
});

test("a lead that was never scored says so instead of showing a zero", () => {
  const t = heatTitle(H("warm", 50, ["email", "phone", "website", "city"], false));
  expect(t).toContain("not scored: ranked on the 4 of 8 real fields known alone");
  expect(t).not.toContain("score 0");
  expect(heatTitle(null)).toBe("Heat not available");
});

test("lanes are counted from the items and filtered by tier", () => {
  const items = [{ id: 1, heat: H("hot", 80, []) }, { id: 2, heat: H("cold", 10, []) }, { id: 3, heat: H("hot", 70, []) }, { id: 4 }];
  expect(laneCounts(items)).toEqual({ top: 0, hot: 2, warm: 0, cold: 1, total: 4 });
  expect(inLane(items, "hot").map((i) => i.id)).toEqual([1, 3]);
  expect(inLane(items, "all")).toHaveLength(4);
  expect(inLane(items, "warm")).toEqual([]);
});

const T = (value, over = {}) => ({ ...H(value >= 65 ? "hot" : "cold", value, ["email"]), top: value >= 80, has_contact: true, ...over });

test("TOP leads are the ones the server flags (heat 80 and more), counted and filtered as a lane, and named in the title", () => {
  const items = [{ id: 1, heat: T(95) }, { id: 2, heat: T(81) }, { id: 3, heat: T(70) }, { id: 4, heat: T(10) }];
  expect(LANES).toEqual(["all", "top", "hot", "warm", "cold"]);
  expect(LANE_LABEL.top).toBe("TOP");
  expect(laneCounts(items)).toMatchObject({ top: 2, hot: 3, cold: 1, total: 4 }); // TOP leads are also hot: the lanes overlap on purpose
  expect(inLane(items, "top").map((i) => i.id)).toEqual([1, 2]);
  expect(heatTitle(T(95))).toContain("TOP lead (heat 80 or more): work it first.");
  expect(heatTitle(T(70))).not.toContain("TOP");
});

test("an empty lead has no e-mail, phone or website according to the server, and is only hidden on that word", () => {
  const empty = { id: 1, heat: T(30, { has_contact: false }) };
  const reachable = { id: 2, heat: T(30) };
  const unknown = { id: 3 }; // the server said nothing: shown, never guessed away
  expect([isEmpty(empty), isEmpty(reachable), isEmpty(unknown)]).toEqual([true, false, false]);
  expect([hasContact(empty), hasContact(reachable), hasContact(unknown)]).toEqual([false, true, true]);
  const items = [empty, reachable, unknown];
  expect(splitEmpty(items, false)).toEqual({ shown: [reachable, unknown], empty: 1 });
  expect(splitEmpty(items, true)).toEqual({ shown: items, empty: 1 });
  expect(splitEmpty([], false)).toEqual({ shown: [], empty: 0 });
});

test("the note says how many empty leads are left out, and nothing when there is none", () => {
  expect(EMPTY_RULE).toBe("no e-mail, phone or website");
  expect(emptyNote(0, false)).toBeNull();
  expect(emptyNote(1, false)).toBe("1 empty lead hidden (no e-mail, phone or website).");
  expect(emptyNote(7, false)).toBe("7 empty leads hidden (no e-mail, phone or website).");
  expect(emptyNote(7, true)).toBe("Showing 7 empty leads (no e-mail, phone or website).");
});
