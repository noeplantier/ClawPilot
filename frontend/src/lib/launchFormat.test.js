import {
  approvableIds,
  confirmText,
  DELIVERY_NOTE,
  exclusionLines,
  gateChips,
  groupExcluded,
  isPlanChanged,
  jobLine,
  launchError,
  limitsLine,
  PLAN_BUTTON,
  planButton,
  progress,
  providerNotice,
  authorizationChip,
  reviewResultText,
  scheduleLine,
  schedulerNotice,
  siteState,
  stageMeta,
  STAGES,
  TRACKING_CHIP,
  TRACKING_ORDER,
} from "@/lib/launchFormat";

const gates = (over = {}) => ({
  provider: { id: "smtp_hostinger", label: "SMTP Hostinger (smtp.hostinger.com)", cold_outreach: "opt_in_required", restriction: "Opt-in explicite requis." },
  dry_run: true, live: false, kill_switch: false, paused: false, sandbox: true, allowlist_size: 0, sender_configured: true,
  max_per_day: 20, max_per_hour: 100, min_delay_seconds: 60, window_start_hour: 8, window_end_hour: 18, timezone: "Europe/Paris",
  sent_today: 0, scheduler: { checked: true, worker_ok: true, beat_ok: true },
  ...over,
});

const plan = (over = {}) => ({
  selected: 100, sendable: 96, blockers: [], warnings: [], exclusions: {}, exclusion_labels: {},
  schedule: { first_at: "2030-06-03T07:00:00Z", last_at: "2030-06-07T15:30:00Z", timezone: "Europe/Paris", days: [{ date: "2030-06-03", count: 20 }, { date: "2030-06-04", count: 20 }] },
  gates: gates(),
  ...over,
});

test("the website has three states and an empty field is never read as 'no website'", () => {
  expect(siteState("site_found").label).toBe("Site présent");
  expect(siteState("none_identified").label).toBe("Aucun site identifié après recherche");
  expect(siteState("unknown").label).toBe("Site inconnu (non vérifié)");
  expect(siteState(undefined)).toBe(siteState("unknown")); // no value: unknown, never a default claim
  expect(siteState("something_new")).toBe(siteState("unknown"));
});

test("the stages follow the journey and each one has a way to be told apart", () => {
  expect(STAGES.map((s) => s.key)).toEqual(["no_draft", "to_review", "blocked", "rejected", "ready", "planned", "launched", "excluded"]);
  expect(stageMeta("ready").label).toBe("Prêts");
  expect(stageMeta("martian").label).toBe("martian");
});

test("tracking never says 'delivered' and says why accepted is not a delivery", () => {
  expect(TRACKING_ORDER).not.toContain("delivered");
  expect(Object.keys(TRACKING_CHIP)).not.toContain("delivered");
  expect(DELIVERY_NOTE).toMatch(/pas une preuve de livraison/);
  expect(DELIVERY_NOTE).toMatch(/jamais marqué « livré »/);
});

test("exclusions are listed from the most frequent, with the server's label, zero counts left out", () => {
  const lines = exclusionLines({ suppressed: 2, provider_requires_opt_in: 40, bounced: 0 }, { suppressed: "Sur la liste de suppression", provider_requires_opt_in: "Non autorisé" });
  expect(lines).toEqual([
    { code: "provider_requires_opt_in", label: "Non autorisé", count: 40 },
    { code: "suppressed", label: "Sur la liste de suppression", count: 2 },
  ]);
  expect(exclusionLines(null, null)).toEqual([]);
  expect(exclusionLines({ x: 1 }, {})[0].label).toBe("x"); // an unknown code is shown as it is, not hidden
});

test("a creation's excluded prospects are grouped by reason", () => {
  const groups = groupExcluded([
    { code: "a", label: "A", name: "n1" }, { code: "b", label: "B", name: "n2" }, { code: "a", label: "A", name: "n3" },
  ]);
  expect(groups.map((g) => [g.code, g.items.length])).toEqual([["a", 2], ["b", 1]]);
});

test("the schedule line gives the count, first and last send, the zone and the number of days", () => {
  const line = scheduleLine(plan().schedule);
  expect(line).toMatch(/^40 messages, du /);
  expect(line).toMatch(/\(heures : Europe\/Paris\), 2 jours$/);
  expect(line).toMatch(/09:00/); // 07:00 UTC is 09:00 in Paris in June
  expect(scheduleLine({ first_at: null, days: [] })).toBe("");
  expect(scheduleLine(null)).toBe("");
});

test("the button is 'Planifier les messages approuvés' and says why it is off", () => {
  expect(PLAN_BUTTON).toBe("Planifier les messages approuvés");
  expect(planButton({ plan: plan(), canDecide: true, busy: false })).toEqual({ disabled: false, reason: null });
  expect(planButton({ plan: null, canDecide: true }).disabled).toBe(true);
  expect(planButton({ plan: plan(), canDecide: false }).reason).toMatch(/propriétaire ou un administrateur/);
  expect(planButton({ plan: plan({ sendable: 0 }), canDecide: true }).reason).toMatch(/Aucun message approuvé/);
  const blocked = plan({ blockers: [{ code: "sender_not_configured", label: "Identité de l'expéditeur non configurée" }] });
  expect(planButton({ plan: blocked, canDecide: true })).toEqual({ disabled: true, reason: "Identité de l'expéditeur non configurée" });
  expect(planButton({ plan: plan(), canDecide: true, busy: true }).disabled).toBe(true);
});

test("the confirmation states the count, one message per recipient, no copy, and that nothing leaves now", () => {
  const text = confirmText(plan());
  expect(text).toMatch(/Planifier 96 messages/);
  expect(text).toMatch(/sans copie ni copie cachée/);
  expect(text).toMatch(/Rien ne part maintenant/);
  expect(text).toMatch(/simulés, rien ne partira/); // dry-run is said
  expect(confirmText(plan({ gates: gates({ dry_run: false }) }))).not.toMatch(/simulés/);
});

test("only drafts waiting for review and free of blockers can be approved in bulk", () => {
  const items = [
    { stage: "to_review", draft: { id: "d1" }, problems: [] },
    { stage: "to_review", draft: { id: "d2" }, problems: [{ blocking: true }] },
    { stage: "to_review", draft: { id: "d3" }, problems: [{ blocking: false }] },
    { stage: "ready", draft: { id: "d4" }, problems: [] },
    { stage: "no_draft", draft: null, problems: [] },
  ];
  expect(approvableIds(items)).toEqual(["d1", "d3"]);
});

test("a review result is one honest sentence, with the first refusal reason", () => {
  expect(reviewResultText({ done: 3, refused: 0, results: [] }, "approve")).toBe("3 brouillons approuvés.");
  expect(reviewResultText({ done: 1, refused: 0 }, "reject")).toBe("1 brouillon rejeté.");
  expect(reviewResultText({ done: 0, refused: 1, results: [{ ok: false, reason: "Variable non résolue : {{prenom}}" }] }, "approve")).toBe(
    "Aucun brouillon modifié ; 1 refusé (Variable non résolue : {{prenom}})."
  );
});

test("errors are sentences; a stale plan asks for a new reading", () => {
  const stale = { response: { status: 409, data: { detail: { code: "plan_changed", message: "95 messages sont envoyables, pas 96", actual: 95 } } } };
  expect(isPlanChanged(stale)).toBe(true);
  expect(launchError(stale)).toMatch(/95 messages sont envoyables, pas 96.*relisez-le/);
  expect(isPlanChanged({ response: { data: { detail: "x" } } })).toBe(false);
  expect(launchError({ response: { status: 409, data: { detail: "Décrivez d'abord votre offre" } } })).toBe("Décrivez d'abord votre offre");
  expect(launchError({ response: { status: 500, data: {} } })).toMatch(/500/);
  expect(launchError({})).toMatch(/injoignable/);
});

test("the provider notice carries the restriction and a quota is never an authorization", () => {
  const notice = providerNotice(gates());
  expect(notice.chip).toBe("chip-danger");
  expect(notice.label).toMatch(/Hostinger.*Opt-in explicite requis/);
  expect(notice.restriction).toBe("Opt-in explicite requis.");
  const unknown = providerNotice(gates({ provider: { id: "smtp", label: "SMTP (x)", cold_outreach: "unverified", restriction: "r" } }));
  expect(unknown.chip).toBe("chip-warn");
  expect(providerNotice(null)).toBeNull();
  const none = providerNotice(gates({ provider: { id: "none", label: "Aucun fournisseur configuré", cold_outreach: "not_configured", restriction: "r" } }));
  expect(none.label).toBe("Aucun fournisseur configuré"); // said once, not twice
});

test("the gate chips repeat what the server says, nothing more", () => {
  const dry = gateChips(gates());
  expect(dry.map((c) => c.key)).toEqual(["dry_run"]);
  const live = gateChips(gates({ dry_run: false, sandbox: true, allowlist_size: 2, kill_switch: true, paused: true, sender_configured: false }));
  expect(live.map((c) => c.key)).toEqual(["live", "sandbox", "kill_switch", "paused", "sender"]);
  expect(live.find((c) => c.key === "sandbox").label).toMatch(/2 adresse/);
  expect(gateChips(gates({ dry_run: false, sandbox: false })).map((c) => c.key)).toContain("sandbox_off");
  expect(gateChips(null)).toEqual([]);
});

test("limits and window are quoted from the server's numbers", () => {
  expect(limitsLine(gates({ timezone_source: "lead_country" }))).toBe("20 par jour · 100 par heure · 60 s minimum entre deux messages · fenêtre 8 h–18 h dans le fuseau de chaque destinataire · jours comptés en Europe/Paris · aujourd'hui : 0 envoyé(s)");
  expect(limitsLine(gates({ timezone_source: "account_default" }))).toMatch(/fenêtre 8 h–18 h \(Europe\/Paris\)/);
});

test("the scheduler is said to be missing instead of hoped for", () => {
  expect(schedulerNotice({ checked: true, worker_ok: true, beat_ok: true }).ok).toBe(true);
  expect(schedulerNotice({ checked: true, worker_ok: false, beat_ok: true }).text).toMatch(/Aucun worker détecté/);
  expect(schedulerNotice({ checked: true, worker_ok: false, beat_ok: false }).text).toMatch(/worker et beat/);
  expect(schedulerNotice({ checked: false }).ok).toBe(false);
  expect(schedulerNotice(undefined).ok).toBe(false);
});

test("progress is empty until something is planned", () => {
  expect(progress({})).toBeNull();
  expect(progress({ scheduled: 3, accepted: 1 })).toEqual({ total: 4, done: 1, percent: 25 });
});

test("the preparation of the missing drafts is told state by state, zero states left out", () => {
  expect(jobLine({ queued: 3, generating: 0, unavailable: 1, failed: 2 })).toBe("3 en file · 1 en attente de l'IA · 2 en échec");
  expect(jobLine({})).toBe("");
});

test("the channel badge states the real basis: a scraped contact without opt-in is never shown as having agreed", () => {
  expect(authorizationChip({ ok: true, basis: "opt_in" })).toEqual({ label: "Opt-in enregistré", chip: "chip-success" });
  expect(authorizationChip({ ok: true, basis: "declared_consent" }).chip).toBe("chip-success");
  expect(authorizationChip({ ok: true, basis: "public_directory" })).toEqual({ label: "Annuaire public, sans opt-in", chip: "chip-warn" });
  expect(authorizationChip({ ok: true, basis: "legitimate_interest_b2b" }).chip).toBe("chip-warn");
  expect(authorizationChip({ ok: false, basis: "public_directory" })).toEqual({ label: "Canal non autorisé", chip: "chip-danger" });
  expect(authorizationChip({ ok: true, basis: "novel" }).chip).toBe("chip-warn"); // an unknown basis is not a success
  expect(authorizationChip(null).label).toBe("Canal non autorisé");
});
