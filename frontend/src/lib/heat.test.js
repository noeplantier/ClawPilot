import { heatTitle, inLane, laneCounts } from "@/lib/heat";

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
  expect(laneCounts(items)).toEqual({ hot: 2, warm: 0, cold: 1, total: 4 });
  expect(inLane(items, "hot").map((i) => i.id)).toEqual([1, 3]);
  expect(inLane(items, "all")).toHaveLength(4);
  expect(inLane(items, "warm")).toEqual([]);
});
