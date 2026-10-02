import {
  auditLabel, blockText, coverageLabel, describeApiError, detailSummary, domainOf, explainTotal, formatRetry,
  limitsPatch, mergeTimeline, scoreBand, validateLimits,
} from "./outreachFormat";

const NOW = new Date("2026-06-01T14:00:00Z");
const axiosError = (status, detail) => ({ response: { status, data: { detail } } });

describe("scoreBand", () => {
  it.each([[null, "none"], [undefined, "none"], [0, "low"], [29, "low"], [30, "medium"], [59, "medium"], [60, "high"], [100, "high"]])(
    "%s -> %s",
    (score, band) => expect(scoreBand(score)).toBe(band)
  );
});

describe("explainTotal", () => {
  const line = (points, weight, state) => ({ points, weight, state });
  it("explains a clamped total and counts what could be observed", () => {
    const t = explainTotal([line(60, 60, "detected"), line(60, 60, "detected"), line(0, 10, "unknown"), line(0, 0, "unknown")]);
    expect(t).toEqual({ raw: 120, capped: 100, clamped: true, weighted: 3, observed: 2 });
  });
  it("does not report a clamp when the sum is in range", () => {
    expect(explainTotal([line(30, 30, "detected")]).clamped).toBe(false);
  });
  it("handles an empty or missing breakdown", () => {
    expect(explainTotal([])).toEqual({ raw: 0, capped: 0, clamped: false, weighted: 0, observed: 0 });
    expect(explainTotal(undefined).raw).toBe(0);
  });
});

describe("small formatters", () => {
  it("coverageLabel", () => {
    expect(coverageLabel(0.714)).toBe("71%");
    expect(coverageLabel(0)).toBe("0%");
    expect(coverageLabel(null)).toBe("—");
  });
  it("domainOf strips scheme, path and www, and rejects junk", () => {
    expect(domainOf("https://www.chez-marcel.example/accueil")).toBe("chez-marcel.example");
    expect(domainOf("chez-marcel.example")).toBe("chez-marcel.example");
    expect(domainOf("")).toBeNull();
    expect(domainOf(null)).toBeNull();
  });
  it("formatRetry words the wait relative to now", () => {
    expect(formatRetry(null, NOW)).toBeNull();
    expect(formatRetry("garbage", NOW)).toBeNull();
    expect(formatRetry("2026-06-01T14:30:00Z", NOW)).toMatch(/^in 30 min/);
    expect(formatRetry("2026-06-01T20:00:00Z", NOW)).toMatch(/^in 6 h/);
    expect(formatRetry("2026-06-01T13:00:00Z", NOW)).toMatch(/^now/);
  });
  it("detailSummary keeps scalars only", () => {
    expect(detailSummary({ from: "pending", to: "approved", nested: { a: 1 }, empty: "", none: null })).toBe("from: pending · to: approved");
    expect(detailSummary(null)).toBe("");
  });
});

describe("describeApiError", () => {
  it("reports an unreachable server", () => {
    expect(describeApiError(new Error("Network Error"), NOW)).toMatch(/Cannot reach the server/);
  });
  it("passes string details through", () => {
    expect(describeApiError(axiosError(409, "Prospect must be approved before a draft is prepared"), NOW)).toBe(
      "Prospect must be approved before a draft is prepared"
    );
  });
  it("explains a coded refusal and when to retry", () => {
    const msg = describeApiError(axiosError(429, { code: "limit_delay", message: "m", retry_at: "2026-06-01T14:10:00Z" }), NOW);
    expect(msg).toMatch(/minimum delay/i);
    expect(msg).toMatch(/try again in 10 min/);
  });
  it("falls back to the server message for an unknown code", () => {
    expect(describeApiError(axiosError(409, { code: "brand_new", message: "Something specific" }), NOW)).toBe("Something specific");
  });
  it("joins FastAPI validation errors", () => {
    const msg = describeApiError(axiosError(422, [{ loc: ["body", "max_per_day"], msg: "must be >= 0" }]), NOW);
    expect(msg).toBe("max_per_day: must be >= 0");
  });
  it("has a message for every refusal code the backend can return", () => {
    ["kill_switch", "paused", "limit_daily", "limit_hourly", "limit_delay", "suppressed", "opted_out", "draft_not_approved",
      "prospect_not_approved", "not_compliant", "live_not_available", "sender_not_configured"].forEach((c) => expect(blockText(c)).toBeTruthy());
  });
});

describe("timeline", () => {
  it("labels audit actions and falls back to the raw action", () => {
    expect(auditLabel("prospect.approved")).toBe("Approved by a reviewer");
    expect(auditLabel("dispatch.blocked", { code: "paused" })).toBe("Dispatch refused: paused");
    expect(auditLabel("something.new")).toBe("something.new");
  });
  it("merges audit and message events newest first and names the actor without exposing ids", () => {
    const audit = [
      { id: "1", action: "prospect.approved", actor_type: "user", actor_user_id: "u1", detail: {}, created_at: "2026-06-01T10:00:00Z" },
      { id: "2", action: "prospect.opted_out", actor_type: "system", actor_user_id: null, detail: {}, created_at: "2026-06-01T12:00:00Z" },
      { id: "3", action: "draft.created", actor_type: "user", actor_user_id: "u2", detail: {}, created_at: "2026-06-01T09:00:00Z" },
    ];
    const messages = [{ events: [{ id: "e1", event_type: "replied", detail: { excerpt: "hi" }, created_at: "2026-06-01T11:00:00Z" }] }];
    const items = mergeTimeline(audit, messages, "u1");
    expect(items.map((i) => i.key)).toEqual(["a-2", "m-e1", "a-1", "a-3"]);
    expect(items[2].actor).toBe("you");
    expect(items[3].actor).toBe("another user");
    expect(items[0].actor).toBe("system");
  });
  it("copes with missing inputs", () => {
    expect(mergeTimeline(undefined, undefined, "u1")).toEqual([]);
  });
});

describe("limits form", () => {
  const ok = { max_per_day: "20", max_per_hour: "100", min_delay_seconds: "60" };
  it("accepts the defaults and the boundaries", () => {
    expect(validateLimits(ok)).toEqual({});
    expect(validateLimits({ max_per_day: "0", max_per_hour: "100000", min_delay_seconds: "86400" })).toEqual({});
  });
  it.each([
    ["max_per_day", "-1"], ["max_per_day", "100001"], ["max_per_hour", "1.5"], ["min_delay_seconds", "86401"], ["min_delay_seconds", ""], ["max_per_day", "abc"],
  ])("rejects %s = %s", (key, value) => expect(validateLimits({ ...ok, [key]: value })[key]).toBeTruthy());
  it("sends only what changed, as numbers", () => {
    const original = { max_per_day: 20, max_per_hour: 100, min_delay_seconds: 60, sending_paused: false };
    expect(limitsPatch(original, ok)).toEqual({});
    expect(limitsPatch(original, { ...ok, max_per_day: "5", min_delay_seconds: "0" })).toEqual({ max_per_day: 5, min_delay_seconds: 0 });
  });
});
