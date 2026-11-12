import { ACK_TEXT, activationBlock, formDefaults, journalLine, remainingLine, statusOf, toPayload, validateForm } from "@/lib/mandateFormat";

const LIMITS = { max_daily: 50, max_total: 100, max_days: 30, zones: 1, min_delay_seconds: 30, min_search_hours: 6 };
const OVERVIEW = (over = {}) => ({ enabled: true, why_disabled: null, reply_collection_configured: true, acknowledgements: ["bounded", "real_sending", "provider_terms", "can_revoke"], limits: LIMITS, ...over });

describe("the four confirmations", () => {
  it("each code the server asks for has its sentence, and the sentences promise nothing", () => {
    for (const code of OVERVIEW().acknowledgements) expect(ACK_TEXT[code].length).toBeGreaterThan(40);
    expect(Object.keys(ACK_TEXT)).toHaveLength(4);
  });
});

describe("activation", () => {
  it("is closed while the mode is off on this server, whatever is ticked", () => {
    const off = OVERVIEW({ enabled: false, why_disabled: "Le mode automatique est désactivé sur ce serveur (FEATURE_AUTOMATION_MAX)" });
    expect(activationBlock(off, Object.keys(ACK_TEXT))).toContain("FEATURE_AUTOMATION_MAX");
  });
  it("is closed while the replies are not read", () => {
    expect(activationBlock(OVERVIEW({ reply_collection_configured: false }), Object.keys(ACK_TEXT))).toContain("IMAP");
  });
  it("asks for every confirmation, counting what is left", () => {
    expect(activationBlock(OVERVIEW(), ["bounded"])).toContain("3 confirmations restantes");
    expect(activationBlock(OVERVIEW(), ["bounded", "real_sending", "provider_terms"])).toContain("1 confirmation restante");
    expect(activationBlock(OVERVIEW(), Object.keys(ACK_TEXT))).toBeNull();
  });
});

describe("the form starts careful and stays inside the server limits", () => {
  it("never proposes more than the server allows", () => {
    const f = formDefaults({ ...LIMITS, max_daily: 10, max_total: 15, max_days: 7 }, { name: "Lyon 6 · restaurants" });
    expect([f.daily_cap, f.total_cap, f.days]).toEqual([10, 15, 7]);
    expect(f.ai_budget).toBe(0); // no AI spending unless the person chooses it
    expect(f.name).toBe("Mandat · Lyon 6 · restaurants");
    expect(validateForm(f, { ...LIMITS, max_daily: 10, max_total: 15, max_days: 7 })).toEqual({});
  });
  it("refuses what the server would refuse, in a sentence per field", () => {
    const f = { ...formDefaults(LIMITS), daily_cap: 80, total_cap: 40, days: 0, min_delay_seconds: 5, window_start_hour: 18, window_end_hour: 8, max_bounce_rate: 0.5 };
    const errors = validateForm(f, LIMITS);
    expect(Object.keys(errors).sort()).toEqual(["daily_cap", "days", "max_bounce_rate", "min_delay_seconds", "window_start_hour"]);
    expect(validateForm({ ...formDefaults(LIMITS), daily_cap: 40, total_cap: 30 }, LIMITS).daily_cap).toContain("dépasser");
    // the most specific sentence wins: outside the server's bound beats "more than the total"
    expect(validateForm({ ...formDefaults(LIMITS), daily_cap: 500, total_cap: 30 }, LIMITS).daily_cap).toContain("de 1 à 50");
  });
  it("sends numbers, the trimmed name and the stop rules", () => {
    const payload = toPayload({ ...formDefaults(LIMITS), name: "  Mon mandat  ", daily_cap: "15" }, "c1");
    expect(payload).toMatchObject({ campaign_id: "c1", name: "Mon mandat", daily_cap: 15, stop_rules: { max_bounce_rate: 0.05, max_opt_out_rate: 0.1, min_sample: 20 } });
    expect(typeof payload.total_cap).toBe("number");
  });
});

describe("status, journal and what is left", () => {
  it("shows the draft as inert and an unknown status as it is", () => {
    expect(statusOf("draft").label).toContain("rien n'agit");
    expect(statusOf("active").tone).toBe("chip-success");
    expect(statusOf("zz").label).toBe("zz");
  });
  it("reads a journal line with the reason in words, who did it, and what left", () => {
    const labels = { kill_switch: "Arrêt d'urgence actif" };
    expect(journalLine({ at: "2026-11-11T10:00:00Z", action: "held", actor: "system", detail: { reason: "kill_switch" } }, labels)).toContain("Rien envoyé ce tour-ci : Arrêt d'urgence actif · automatique");
    expect(journalLine({ at: "2026-11-11T10:00:00Z", action: "run", actor: "system", detail: { sent: 1 } })).toContain("1 envoyé ·");
    expect(journalLine({ at: "2026-11-11T10:00:00Z", action: "activated", actor: "user", detail: {} })).toContain("par une personne");
    expect(journalLine({ at: "2026-11-11T10:00:00Z", action: "unknown_action", actor: "system" })).toContain("unknown_action");
  });
  it("says what is left of the limits, or nothing without a report", () => {
    expect(remainingLine({ remaining: { messages: 1, days: 1 } })).toBe("Il reste 1 message et 1 jour avant l'expiration.");
    expect(remainingLine({ remaining: { messages: 80, days: 12 } })).toContain("80 messages et 12 jours");
    expect(remainingLine(null)).toBe("");
  });
});
