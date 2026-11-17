import { basisLine, createLabel, emptyText, highScoreLabel, KIND_LABEL, readyLine } from "@/lib/suggestions";

const S = (over) => ({ eligible: 0, total: 5, blocked_reason: null, ...over });

test("a suggestion says how many can really join, or what blocks it", () => {
  expect(readyLine(S({ eligible: 3 }))).toBe("3 sur 5 peuvent rejoindre une campagne aujourd'hui");
  expect(readyLine(S({ blocked_reason: "Live sending is off (dry-run)." }))).toBe("Live sending is off (dry-run).");
  expect(readyLine(S())).toBe("Personne dans ce groupe ne peut encore recevoir de message.");
});

test("the button never promises a draft that cannot hold anyone", () => {
  expect(createLabel(S({ eligible: 2 }), false)).toBe("CRÉER LE BROUILLON · 2");
  expect(createLabel(S(), false)).toBe("PAS ENCORE PRÊT");
  expect(createLabel(S({ eligible: 2 }), true)).toBe("CRÉATION…");
});

test("a heat ranking is called a high score, never « hot » (hot is an observed intent)", () => {
  expect(highScoreLabel(1)).toBe("1 score élevé");
  expect(highScoreLabel(3)).toBe("3 scores élevés");
  expect(Object.values(KIND_LABEL).join(" ")).not.toMatch(/hot/i);
});

test("what the suggestions are computed from is stated, and the empty state is explicit", () => {
  expect(basisLine({ prospects: 1, leads: 2 })).toBe("Calculé à partir de 1 prospect et 2 leads du CRM.");
  expect(basisLine(null)).toBe("");
  expect(emptyText({ prospects: 0, leads: 0 })).toContain("elles apparaissent dès que");
  expect(emptyText({ prospects: 4, leads: 0 })).toContain("apparaissent d'elles-mêmes");
});
