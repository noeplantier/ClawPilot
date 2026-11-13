import { costText, meter, messagesLeft, tightest, untilText } from "@/lib/creditsFormat";

const NOW = new Date("2026-11-13T09:00:00Z");

test("a window shows what the server counted, and when it resets", () => {
  const m = meter({ key: "session", limit: 30, used: 24, resets_at: "2026-11-13T11:14:00Z" }, NOW);
  expect(m).toMatchObject({ pct: 80, tone: "warn", remaining: 6, label: "24 / 30 crédits" });
  expect(m.reset).toBe("Réinitialisation dans 2 h 14 min (12:14)"); // Paris time
  expect(meter({ key: "session", limit: 30, used: 0, resets_at: null }, NOW).reset).toMatch(/Aucune session en cours/);
  expect(meter({ key: "day", limit: 100, used: 0, resets_at: null }, NOW).reset).toBe("Rien d'utilisé aujourd'hui.");
  expect(meter({ key: "day", limit: 10, used: 12, resets_at: null }, NOW)).toMatchObject({ pct: 100, tone: "danger", remaining: 0 });
});

test("the time left is said plainly", () => {
  expect(untilText("2026-11-13T09:12:00Z", NOW)).toBe("dans 12 min");
  expect(untilText("2026-11-13T11:00:00Z", NOW)).toBe("dans 2 h");
  expect(untilText("2026-11-13T08:00:00Z", NOW)).toBe("maintenant");
});

test("the sidebar shows the tightest window", () => {
  const w = [{ key: "session", limit: 30, used: 3 }, { key: "day", limit: 100, used: 50 }];
  expect(tightest(w).key).toBe("day");
  expect(tightest([])).toBeNull();
});

test("a model says its cost and how many messages are left", () => {
  const w = [{ key: "session", limit: 30, used: 25 }, { key: "day", limit: 100, used: 10 }];
  expect(costText({ credits: 0 })).toBe("0 crédit · sans IA");
  expect(costText({ credits: 2 })).toBe("2 crédits par message");
  expect(messagesLeft({ credits: 2 }, w)).toBe("2 messages possibles maintenant");
  expect(messagesLeft({ credits: 0 }, w)).toMatch(/illimité/);
});
