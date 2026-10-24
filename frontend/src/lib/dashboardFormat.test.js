import { chartGeometry, DASH, ago, kpiCards, modeOf, pct, quotaShare, seriesHasData, seriesSummary, shortDay } from "@/lib/dashboardFormat";

const K = { prospects: 3, pending_review: 2, approved: 1, scored: 3, avg_score: 41.5, sent_today: 2, messages: 4, replies: 1, reply_rate: 0.25, bounces: 0, bounce_rate: 0, unsubscribed: 1 };
const L = { dry_run: true, kill_switch: false, paused: false, smtp_configured: false, sandbox: true, allowlist_size: 0, max_per_day: 20, sent_today: 2, remaining_today: 18 };

test("null means unknown and is never shown as zero", () => {
  expect(pct(null)).toBe(DASH);
  expect(pct(0)).toBe("0%");
  expect(pct(0.256)).toBe("25.6%");
  const empty = kpiCards({ ...K, prospects: 0, pending_review: 0, approved: 0, scored: 0, avg_score: null, messages: 0, reply_rate: null, bounce_rate: null }, L);
  const byKey = Object.fromEntries(empty.map((c) => [c.key, c]));
  expect(byKey.avg_score.value).toBe(DASH);
  expect(byKey.avg_score.hint).toBe("nothing scored yet");
  expect(byKey.replies.hint).toBe("no message sent yet");
});

test("cards carry the real counts and the remaining quota", () => {
  const byKey = Object.fromEntries(kpiCards(K, L).map((c) => [c.key, c]));
  expect(byKey.sent_today.hint).toBe("18 left of 20 allowed");
  expect(byKey.replies.hint).toBe("25% of 4 sent");
  expect(byKey.prospects.hint).toBe("2 pending review · 1 approved");
});

test("the most restrictive sending state wins", () => {
  expect(modeOf({ ...L, kill_switch: true, paused: true }).label).toMatch(/KILL SWITCH/);
  expect(modeOf({ ...L, paused: true }).label).toBe("PAUSED");
  expect(modeOf(L).label).toBe("DRY-RUN");
  expect(modeOf({ ...L, dry_run: false }).label).toMatch(/SMTP INCOMPLETE/);
  expect(modeOf({ ...L, dry_run: false, smtp_configured: true, allowlist_size: 2 }).label).toBe("LIVE · SANDBOX (2 ALLOWED)");
  expect(modeOf({ ...L, dry_run: false, smtp_configured: true, sandbox: false }).tone).toBe("danger");
});

test("quota share is bounded and a zero cap counts as full", () => {
  expect(quotaShare({ max_per_day: 20, sent_today: 5 })).toBe(0.25);
  expect(quotaShare({ max_per_day: 2, sent_today: 5 })).toBe(1);
  expect(quotaShare({ max_per_day: 0, sent_today: 0 })).toBe(1);
});

test("series helpers", () => {
  const empty = [{ date: "2026-10-01", sent: 0, replied: 0 }];
  expect(seriesHasData(empty)).toBe(false);
  const some = [{ date: "2026-10-01", sent: 2, replied: 1 }, { date: "2026-10-02", sent: 0, replied: 0 }];
  expect(seriesHasData(some)).toBe(true);
  expect(seriesSummary(some)).toBe("2 messages sent and 1 reply over the last 2 days (UTC)");
  expect(shortDay("2026-10-03")).toBe("03/10");
});

test("relative time", () => {
  const now = new Date("2026-10-03T12:00:00Z");
  expect(ago("2026-10-03T11:59:40Z", now)).toBe("just now");
  expect(ago("2026-10-03T11:30:00Z", now)).toBe("30 min ago");
  expect(ago("2026-10-03T09:00:00Z", now)).toBe("3 h ago");
  expect(ago("2026-10-01T12:00:00Z", now)).toBe("2 d ago");
});

describe("chartGeometry", () => {
  const series = [{ date: "2026-10-01", sent: 0, replied: 0 }, { date: "2026-10-02", sent: 3, replied: 1 }, { date: "2026-10-03", sent: 2, replied: 0 }];
  test("the scale starts at 0 and ends on an integer tick at or above the maximum", () => {
    const g = chartGeometry(series);
    expect(g.ticks[0]).toBe(0);
    expect(g.ticks[g.ticks.length - 1]).toBeGreaterThanOrEqual(3);
    expect(g.ticks.every(Number.isInteger)).toBe(true);
    expect(g.y(0)).toBeGreaterThan(g.y(g.max)); // bigger values are higher on the screen
  });
  test("points are spread left to right, one per day, and an empty series does not break", () => {
    const g = chartGeometry(series);
    expect(g.x(0)).toBeLessThan(g.x(1));
    expect(g.x(1)).toBeLessThan(g.x(2));
    expect(g.line("sent").split(" ")).toHaveLength(3);
    expect(() => chartGeometry([{ date: "2026-10-01", sent: 0, replied: 0 }])).not.toThrow();
    expect(chartGeometry([{ date: "2026-10-01", sent: 0, replied: 0 }]).max).toBe(1);
  });
});
