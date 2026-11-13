import { ACK_LABELS, frequencyLabel, missingRequirements, runSummary } from "@/lib/autopilotFormat";

test("every acknowledgement of the server has a sentence", () => {
  expect(Object.keys(ACK_LABELS)).toEqual(["b2b_use", "auto_approve", "ai_credits", "can_stop"]);
});

test("the missing switches are named, never guessed", () => {
  expect(missingRequirements({ external_sources: true, prospect_import: true, automation_max: true, live_sending: true })).toEqual([]);
  const missing = missingRequirements({ external_sources: false, prospect_import: true, automation_max: true, live_sending: false });
  expect(missing.map((m) => m.fix)).toEqual(["FEATURE_EXTERNAL_SOURCES=true", "FEATURE_LIVE_SENDING=true"]);
  expect(missingRequirements(null)).toEqual([]);
});

test("a run is told from the server's counts, and it never sent anything", () => {
  const line = runSummary({ discovery: { search: "ok", found: 12, reachable: 4, created: 3 }, approval: { approved: 3 }, drafts: { ready: 2 } });
  expect(line).toBe("12 lieu(x) trouvé(s), 4 joignable(s), 3 ajouté(s) · 3 prospect(s) approuvé(s) · 2 brouillon(s) prêt(s). Rien n'a été envoyé par le pilote.");
  expect(runSummary({ discovery: { search: "skipped", why: "FEATURE_EXTERNAL_SOURCES est désactivé" } })).toMatch(/^Recherche non lancée/);
  expect(runSummary({})).toBe("Rien à faire pour l'instant.");
});

test("frequencies read naturally", () => {
  expect(frequencyLabel(6)).toBe("toutes les 6 h");
  expect(frequencyLabel(24)).toBe("toutes les 24 h");
  expect(frequencyLabel(72)).toBe("tous les 3 jours");
});
