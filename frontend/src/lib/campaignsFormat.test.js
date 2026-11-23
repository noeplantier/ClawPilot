import { CATEGORIES, confirmLines, groupCampaigns, nextAction, progressOf } from "@/lib/campaignsFormat";

const C = (over) => ({ id: "c", name: "Lyon", status: "draft", steps: [], lead_ids: [], sent: 0, ...over });

test("campaigns are grouped by their real status, in the order of the flow, empty groups left out", () => {
  const groups = groupCampaigns([C({ id: "a", status: "running" }), C({ id: "b" }), C({ id: "c", status: "weird" })]);
  expect(groups.map((g) => g.key)).toEqual(["draft", "running"]);
  expect(groups.flatMap((g) => g.items.map((c) => c.id))).toEqual(["b", "a"]); // an unknown status is never forced into a group
  expect(groupCampaigns(null)).toEqual([]);
  expect(CATEGORIES.map((c) => c.label)).toEqual(["Brouillons", "En cours", "En pause", "Terminées"]);
});

test("progress is accepted messages over planned messages, never a ratio without recipients or steps", () => {
  expect(progressOf(C())).toMatchObject({ pct: null, text: "Aucun destinataire assigné" });
  expect(progressOf(C({ lead_ids: ["1", "2"] }))).toMatchObject({ pct: null, text: "2 destinataires, aucune étape écrite" });
  const p = progressOf(C({ lead_ids: ["1", "2"], steps: [{}, {}], sent: 1 }));
  expect(p).toEqual({ accepted: 1, planned: 4, pct: 25, text: "1 accepté par le fournisseur sur 4 messages prévus" });
  expect(p.text).not.toMatch(/livr|deliver/i);
  expect(progressOf(C({ lead_ids: ["1"], steps: [{}], sent: 9 })).pct).toBe(100);
});

test("one decisive next action, and a draft is never launched before it has steps and recipients", () => {
  expect(nextAction(C()).key).toBe("edit");
  expect(nextAction(C({ steps: [{}] })).key).toBe("open");
  expect(nextAction(C({ steps: [{}], lead_ids: ["1"] }))).toEqual({ key: "launch", label: "LANCER…" });
  expect(nextAction(C({ status: "running" })).key).toBe("pause");
  expect(nextAction(C({ status: "paused" })).key).toBe("resume");
  expect(nextAction(C({ status: "completed" })).key).toBe("open");
});

test("the confirmation says what leaves, to how many, one by one, under every gate, and that accepted is not delivered", () => {
  const text = confirmLines(C({ lead_ids: ["1", "2", "3"] }), "launch").join(" ");
  expect(text).toContain("3 destinataires");
  expect(text).toContain("aucune copie (CC/CCI)");
  expect(text).toMatch(/arrêt d'urgence/);
  expect(text).toContain("ne veut pas dire « livré »");
  expect(confirmLines(C({ lead_ids: ["1"] }), "resume")[0]).toContain("étapes restantes");
});
