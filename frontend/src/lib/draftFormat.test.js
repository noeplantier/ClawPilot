import { DRAFT_JOB_META, GAP_LABEL, SITE_STATE_LABEL, draftSummaryLine, gapLine } from "@/lib/outreachFormat";

test("what is missing is said in plain words, in the server's order, and an unknown code is never hidden", () => {
  expect(gapLine(["email_missing", "address_missing"])).toBe("Missing: e-mail, address");
  expect(gapLine(["coordinates_missing"])).toBe("Missing: position on the map");
  expect(gapLine(["something_new"])).toBe("Missing: something_new");
  expect(gapLine([])).toBe("Nothing missing");
  expect(Object.keys(GAP_LABEL)).toHaveLength(12); // every gap the policy can name has a label
});

test("every draft state has a label and the site states never overstate what is known", () => {
  for (const state of ["queued", "generating", "ready", "failed", "unavailable", "offer_required"]) {
    expect(DRAFT_JOB_META[state].label).toBeTruthy();
  }
  expect(DRAFT_JOB_META.offer_required.label).toBe("Offer required");
  expect(SITE_STATE_LABEL.unknown).toBe("Website not checked"); // never "no website"
  expect(SITE_STATE_LABEL.none_identified).toContain("identified");
});

test("the batch summary lists the states present and nothing invented", () => {
  const counts = { queued: 0, generating: 2, ready: 3, failed: 0, unavailable: 1, offer_required: 0 };
  expect(draftSummaryLine({ counts })).toBe("3 ready · 2 being written · 1 waiting for the AI");
  expect(draftSummaryLine({ counts: { queued: 0, generating: 0, ready: 0, failed: 0, unavailable: 0, offer_required: 0 } })).toBe("No draft prepared yet");
  expect(draftSummaryLine(null)).toBe("");
});
