import {
  approvalState, approveBlock, exclusionRows, insertToken, journeyStatus, progressLine, readinessView, scheduleLine, trackingRows, volumeLine, zoneFromSearch,
} from "@/lib/journeyFormat";

const ITEM = (id, ok, blocking, extra = {}) => ({ id, ok, blocking, label: id, fix: ok ? null : `fix ${id}`, ...extra });
const SUMMARY = (over = {}) => ({
  readiness: { ready: true, items: [] },
  template: { problems: [] },
  audience: { sendable: 12, held_back_count: 0, exclusions: {}, exclusion_labels: {} },
  approval: { approved: false },
  ...over,
});

describe("the zone carried by the address", () => {
  it("is the box and the category, only when they are coherent", () => {
    expect(zoneFromSearch("?south=45.7&west=4.78&north=45.8&east=4.9&category=restaurant")).toEqual({ south: 45.7, west: 4.78, north: 45.8, east: 4.9, category: "restaurant" });
    expect(zoneFromSearch("?south=45.7&west=4.78&north=45.8&east=4.9&category=bar&label=Lyon%206").label).toBe("Lyon 6");
    expect(zoneFromSearch("")).toBeNull();
    expect(zoneFromSearch("?south=45.8&west=4.78&north=45.7&east=4.9&category=bar")).toBeNull(); // inverted
    expect(zoneFromSearch("?south=45.7&west=4.78&north=45.8&east=4.9")).toBeNull(); // no category
    expect(zoneFromSearch("?south=&west=4.78&north=45.8&east=4.9&category=bar")).toBeNull(); // an empty value is not 0
    expect(zoneFromSearch("?south=x&west=4.78&north=45.8&east=4.9&category=bar")).toBeNull();
    expect(zoneFromSearch("?south=-95&west=4.78&north=45.8&east=4.9&category=bar")).toBeNull();
  });
});

describe("the one-time setup", () => {
  it("puts what blocks first, with its exact fix, and keeps what only informs apart", () => {
    const view = readinessView({ ready: false, items: [ITEM("offer", false, true), ITEM("identity", true, true), ITEM("replies", false, false), ITEM("mode", true, false, { note: "Sandbox actif" })] });
    expect(view.ready).toBe(false);
    expect(view.blockers.map((i) => i.id)).toEqual(["offer"]);
    expect(view.blockers[0].fix).toBe("fix offer");
    expect(view.warnings.map((i) => i.id)).toEqual(["replies"]);
    expect(view.notes.map((i) => i.id)).toEqual(["mode"]);
    expect([view.done, view.total]).toEqual([2, 4]);
  });
  it("tolerates an empty answer", () => {
    expect(readinessView(null)).toMatchObject({ ready: false, blockers: [], total: 0 });
  });
});

describe("the approval is never shown as valid when it no longer covers what is displayed", () => {
  it("tells the four states", () => {
    expect(approvalState({ approved: false }).key).toBe("none");
    expect(approvalState({ approved: true, revoked_at: "2026-11-11T10:00:00Z", valid: false }).key).toBe("revoked");
    const stale = approvalState({ approved: true, valid: false, reasons: [{ code: "template_changed", label: "Le message a changé depuis l'approbation." }] });
    expect(stale.key).toBe("stale");
    expect(stale.label).toContain("Le message a changé");
    expect(approvalState({ approved: true, valid: true, template_version: 3 })).toMatchObject({ key: "valid", label: "Approuvée pour la version 3 du message" });
    expect(approvalState(undefined).key).toBe("none");
  });
});

describe("why the approve button is closed", () => {
  it("is null only when the person may approve a version that can leave", () => {
    expect(approveBlock(SUMMARY())).toBeNull();
  });
  it("names the first blocker, in order", () => {
    expect(approveBlock(null)).toBe("Chargement…");
    expect(approveBlock(SUMMARY(), false)).toContain("propriétaire");
    expect(approveBlock(SUMMARY({ readiness: { ready: false, items: [] } }))).toContain("configuration");
    expect(approveBlock(SUMMARY({ template: { problems: [{ code: "x", label: "y" }] } }))).toContain("Corrigez le message");
    expect(approveBlock(SUMMARY({ audience: { sendable: 0, held_back_count: 3 } }))).toContain("retenus");
    expect(approveBlock(SUMMARY({ audience: { sendable: 0, held_back_count: 0 } }))).toContain("Aucun établissement");
    expect(approveBlock(SUMMARY({ approval: { approved: true, valid: true, template_version: 1 } }))).toBe("Cette version est déjà approuvée.");
  });
});

describe("volume, schedule and exclusions are the server's numbers", () => {
  it("reads the volume with its caps", () => {
    expect(volumeLine({ messages: 1, daily_cap: 20, total_cap: 1 })).toBe("1 message, un par destinataire · au plus 20 par jour · plafond total 1.");
    expect(volumeLine({ messages: 40, daily_cap: 20, total_cap: 40 })).toContain("40 messages");
    expect(volumeLine(null)).toBe("");
  });
  it("says there is nothing to plan, or when it starts and ends", () => {
    expect(scheduleLine({ first_at: null })).toBe("Aucun envoi à planifier.");
    const line = scheduleLine({ first_at: "2026-11-12T08:00:00Z", last_at: "2026-11-13T10:00:00Z", timezone: "Europe/Paris", days: [{ date: "2026-11-12", count: 20 }, { date: "2026-11-13", count: 20 }] });
    expect(line).toContain("sur 2 jours");
    expect(line).toContain("Europe/Paris");
    expect(line).toContain("revérifie chaque envoi");
  });
  it("lists the exclusions from the largest, with their labels, and drops the empty ones", () => {
    const rows = exclusionRows({ exclusions: { no_email: 2, opted_out: 5, other: 0 }, exclusion_labels: { no_email: "Sans e-mail", opted_out: "Opposition" } });
    expect(rows).toEqual([{ code: "opted_out", count: 5, label: "Opposition" }, { code: "no_email", count: 2, label: "Sans e-mail" }]);
    expect(exclusionRows(undefined)).toEqual([]);
  });
});

describe("the follow-up never says delivered", () => {
  it("names what the system really knows", () => {
    const rows = trackingRows({ scheduled: 5, accepted: 3, replied: 1, delivered: 0, unknown: 1 });
    expect(rows.map((r) => r.label)).toEqual(["Planifiés", "Acceptés par le serveur SMTP", "Réponses", "Résultat inconnu"]);
    expect(JSON.stringify(rows).toLowerCase()).not.toContain("livré");
    expect(trackingRows(undefined)).toEqual([]);
  });
  it("reads the progress, or says nothing is planned", () => {
    expect(progressLine({ total: 0 })).toBe("Rien n'est planifié pour l'instant.");
    expect(progressLine({ total: 20, done: 5, percent: 25 })).toBe("5 sur 20 traités (25 %).");
    expect(progressLine({ total: 20, done: 5, percent: null })).toBe("5 sur 20 traités.");
  });
  it("names the campaign statuses and leaves an unknown one as it is", () => {
    expect(journeyStatus("running")).toBe("En cours");
    expect(journeyStatus("paused")).toBe("En pause");
    expect(journeyStatus("weird")).toBe("weird");
  });
});

describe("a merge field is inserted at the cursor", () => {
  it("replaces the selection and moves the caret after the token", () => {
    expect(insertToken("Bonjour ,", 8, 8, "{{name}}")).toEqual({ text: "Bonjour {{name}},", caret: 16 });
    expect(insertToken("Bonjour XX,", 8, 10, "{{name}}").text).toBe("Bonjour {{name}},");
    expect(insertToken("abc", undefined, undefined, "!")).toEqual({ text: "abc!", caret: 4 });
    expect(insertToken("abc", 99, 120, "!").text).toBe("abc!");
  });
});
