import { checks, coolingLine, jobRunsLine, jobsLine, probeLine } from "@/lib/systemHealth";

const REPORT = (over = {}) => ({
  database: { ok: true, kind: "supabase_session_pooler", port: "5432", latency_ms: 12 },
  migrations: { ok: true, current: "a8c4d5e6f7b9", head: "a8c4d5e6f7b9" },
  cache: { ok: true, live_entries: 1 },
  public_page_cache: { ok: true, live_entries: 2 },
  workers: { ok: true, active_count: 1, automation_queue: true },
  beat: { ok: true, last_tick_at: "2026-10-25T00:00:00Z", age_seconds: 20 },
  automation_queue: { broker_ok: true, pending: 0 },
  integrations: { smtp: { status: "configured" }, imap: { status: "configured" }, groq: { status: "configured" } },
  ...over,
});

test("a healthy report is all green and says where the data lives", () => {
  const rows = checks(REPORT());
  expect(rows.every((r) => r.ok)).toBe(true);
  expect(rows[0].detail).toContain("Supabase (session pooler)");
  expect(rows[2].detail).toBe("1 live entry");
  expect(rows.find((r) => r.key === "workers").ok).toBe(true);
  expect(rows.find((r) => r.key === "beat").ok).toBe(true);
  expect(rows.find((r) => r.key === "imap").ok).toBe(true);
});

test("a database that cannot work from this host is reported as a problem with the fix", () => {
  const direct = checks(REPORT({ database: { ok: true, kind: "supabase_direct", latency_ms: 5 } }))[0];
  expect(direct.ok).toBe(false);
  expect(direct.detail).toContain("session pooler");
  const tx = checks(REPORT({ database: { ok: true, kind: "supabase_transaction_pooler", latency_ms: 5 } }))[0];
  expect(tx.ok).toBe(false);
});

test("pending migrations show both versions", () => {
  const row = checks(REPORT({ migrations: { ok: false, current: "old", head: "new" } }))[1];
  expect(row.ok).toBe(false);
  expect(row.detail).toBe("database at old, code expects new");
  expect(checks(null)).toEqual([]);
});

test("job counts and probe results are read as they are", () => {
  expect(jobsLine({})).toBe("No map search in the last 24 hours.");
  expect(jobsLine({ succeeded: 2, failed: 1 })).toBe("3 searches in 24 h: 2 succeeded, 1 failed.");
  expect(jobRunsLine({})).toBe("No persisted job runs in the last 24 hours.");
  expect(jobRunsLine({ succeeded: 2, failed: 1 })).toBe("3 persisted job run(s) in 24 h: 2 succeeded, 1 failed.");
  expect(probeLine({ host: "a.example", ok: true, status: 200, ms: 40 })).toBe("a.example: reachable (HTTP 200, 40 ms)");
  expect(probeLine({ host: "b.example", ok: false, status: 429, ms: 9 })).toBe("b.example: answered HTTP 429 (9 ms)");
  expect(probeLine({ host: "c.example", ok: false, error: "OSError: Network is unreachable", ms: 3 })).toBe("c.example: OSError: Network is unreachable (3 ms)");
});

test("servers that failed recently are named, and nothing is said when all is well", () => {
  expect(coolingLine([])).toBe("");
  expect(coolingLine(undefined)).toBe("");
  expect(coolingLine(["a.example", "b.example"])).toBe("Failed recently, now tried last: a.example, b.example.");
});

test("health reports expose actual configuration state without treating it as a live mail or AI probe", () => {
  const rows = checks(REPORT({ integrations: { smtp: { status: "configured" }, imap: { status: "configured" }, groq: { status: "configured" } } }));
  expect(rows.filter((row) => ["smtp", "imap", "groq"].includes(row.key)).every((row) => row.detail.includes("not probed"))).toBe(true);
});
