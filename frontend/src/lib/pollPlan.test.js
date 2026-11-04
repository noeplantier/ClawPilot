import { BASE_MS, BURST_MS, BURST_WINDOW_MS, HIDDEN_RECHECK_MS, MAX_BACKOFF_MS, nextDelay, startBurst, withSecondary } from "./pollPlan";

describe("the refresh rhythm of a live view", () => {
  test("idle it asks every few seconds, in a burst every two seconds", () => {
    expect(nextDelay({ now: 1000 })).toBe(BASE_MS);
    expect(nextDelay({ now: 1000, burstUntil: 5000 })).toBe(BURST_MS);
    expect(nextDelay({ now: 5000, burstUntil: 5000 })).toBe(BASE_MS); // the burst is over
  });

  test("a burst lasts a bounded time and never shortens a running one", () => {
    expect(startBurst(1000)).toBe(1000 + BURST_WINDOW_MS);
    expect(startBurst(2000, 1000 + BURST_WINDOW_MS)).toBe(2000 + BURST_WINDOW_MS);
    expect(startBurst(1000, 900000)).toBe(900000);
  });

  test("a hidden tab is not hammered and a failing server is asked less, never harder", () => {
    expect(nextDelay({ now: 0, hidden: true, burstUntil: 99999 })).toBe(HIDDEN_RECHECK_MS);
    expect(nextDelay({ now: 0, failures: 1 })).toBe(BASE_MS * 2);
    expect(nextDelay({ now: 0, failures: 20 })).toBe(MAX_BACKOFF_MS);
    expect(nextDelay({ now: 0, burstUntil: 5000, failures: 2 })).toBe(BURST_MS * 4);
  });

  test("the slow counters load first, then on every third refresh", () => {
    expect([0, 1, 2, 3, 4, 5, 6].filter(withSecondary)).toEqual([0, 3, 6]);
  });
});
