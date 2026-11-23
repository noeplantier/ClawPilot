import { BLOCKED_REASON, lastDispatchText, retryText, statusSummary } from "@/lib/sendingFormat";

const STATUS = { dry_run: true, kill_switch: false, paused: false, sent_today: 3, sent_last_hour: 1, last_dispatched_at: null, next_allowed_at: null, blocked_by: null };
const NOW = new Date("2026-11-20T10:00:00Z");

describe("the decision comes first", () => {
  it("says a message can leave now, and whether for real", () => {
    expect(statusSummary(STATUS, { sender_configured: true }, NOW).headline).toBe("Envoi possible maintenant, en simulation : rien ne part réellement.");
    expect(statusSummary({ ...STATUS, dry_run: false }, { sender_configured: true }, NOW).headline).toBe("Envoi possible maintenant : les messages partent pour de vrai.");
  });
  it("says why it is blocked, in words, with the retry time when the server gives one", () => {
    const s = statusSummary({ ...STATUS, blocked_by: "daily", next_allowed_at: "2026-11-20T10:12:00Z" }, null, NOW);
    expect(s.canSend).toBe(false);
    expect(s.headline).toMatch(/^Envoi bloqué : limite du jour atteinte · réessai à \d\d:\d\d \(dans 12 min\)\.$/);
    expect(statusSummary({ ...STATUS, blocked_by: "kill_switch" }, null, NOW).headline).toBe(`Envoi bloqué : ${BLOCKED_REASON.kill_switch}.`);
    expect(statusSummary({ ...STATUS, blocked_by: "new_code" }, null, NOW).headline).toBe("Envoi bloqué : new_code."); // unknown: shown as is
  });
  it("is nothing until the status is loaded", () => {
    expect(statusSummary(null, null)).toBeNull();
  });
});

describe("chips and volumes come from the server, never invented", () => {
  it("shows the mode, the emergency stop, the pause and the sender identity", () => {
    const chips = statusSummary({ ...STATUS, kill_switch: true, paused: true }, { sender_configured: false }, NOW).chips;
    expect(chips.map((c) => [c.testId, c.label, c.tone])).toEqual([
      ["fact-mode", "Simulation : rien ne part", "chip-cold"],
      ["fact-kill", "Arrêt d'urgence : ACTIVÉ", "chip-danger"],
      ["fact-paused", "Compte : en pause", "chip-warn"],
      ["fact-sender", "Identité d'expéditeur : non configurée", "chip-danger"],
    ]);
    expect(statusSummary(STATUS, null, NOW).chips[3].label).toBe("Identité d'expéditeur : —"); // settings not loaded: unknown, not "no"
  });
  it("prints a missing count as « — », never 0, and says when nothing was sent yet", () => {
    const v = statusSummary({ ...STATUS, sent_today: undefined, sent_last_hour: 0 }, null, NOW).volumes;
    expect(v.map((x) => x.value)).toEqual(["—", "0", "aucun pour l'instant"]);
    expect(lastDispatchText("not a date")).toBe("—");
  });
  it("words the retry for now, minutes and hours", () => {
    expect(retryText("2026-11-20T09:59:00Z", NOW)).toMatch(/^réessai possible maintenant/);
    expect(retryText("2026-11-20T13:00:00Z", NOW)).toMatch(/\(dans 3 h\)$/);
    expect(retryText(null, NOW)).toBeNull();
  });
});
