import { basisLine, createLabel, emptyText, readyLine } from "@/lib/suggestions";

const S = (over) => ({ eligible: 0, total: 5, blocked_reason: null, ...over });

test("a suggestion says how many can really join, or what blocks it", () => {
  expect(readyLine(S({ eligible: 3 }))).toBe("3 of 5 can join a campaign today");
  expect(readyLine(S({ blocked_reason: "Live sending is off (dry-run)." }))).toBe("Live sending is off (dry-run).");
  expect(readyLine(S())).toBe("Nobody in this group can receive a message yet.");
});

test("the button never promises a draft that cannot hold anyone", () => {
  expect(createLabel(S({ eligible: 2 }), false)).toBe("CREATE DRAFT · 2");
  expect(createLabel(S(), false)).toBe("NOT READY");
  expect(createLabel(S({ eligible: 2 }), true)).toBe("CREATING…");
});

test("what the suggestions are computed from is stated, and the empty state is explicit", () => {
  expect(basisLine({ prospects: 1, leads: 2 })).toBe("Computed from 1 prospect and 2 CRM leads.");
  expect(basisLine(null)).toBe("");
  expect(emptyText({ prospects: 0, leads: 0 })).toContain("they appear once you have prospects or leads");
  expect(emptyText({ prospects: 4, leads: 0 })).toContain("Suggestions appear on their own");
});
