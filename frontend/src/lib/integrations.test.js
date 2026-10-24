import { effective, groupItems, needsList, summarize, testGeocoder, testable } from "@/lib/integrations";

const item = (over) => ({ id: "smtp", group: "sending", status: "unchecked", label: "CONFIGURED · NOT TESTED", needs: [], test: "server", ...over });

describe("integrations helpers", () => {
  it("groups entries in a fixed order and drops empty groups", () => {
    const groups = groupItems([item({ id: "ai", group: "ai" }), item({ id: "database", group: "data" })]);
    expect(groups.map(([key]) => key)).toEqual(["data", "ai"]);
  });

  it("keeps the server's status unless a test ran and answered", () => {
    expect(effective(item(), undefined)).toEqual({ status: "unchecked", label: "CONFIGURED · NOT TESTED" });
    expect(effective(item(), { outcome: "skipped" }).status).toBe("unchecked");
    expect(effective(item(), { outcome: "passed", latency_ms: 41 })).toEqual({ status: "ready", label: "VERIFIED · 41 ms" });
  });

  it("a failed test is danger for a sender and only partial for a service with a fallback", () => {
    expect(effective(item({ id: "smtp" }), { outcome: "failed" }).status).toBe("blocked");
    expect(effective(item({ id: "osm" }), { outcome: "failed" }).status).toBe("partial");
    expect(effective(item({ id: "geocoder" }), { outcome: "failed" }).status).toBe("partial");
  });

  it("counts what needs attention and never counts an unverified service as ready", () => {
    const items = [item({ id: "a", status: "ready" }), item({ id: "b", status: "unchecked" }), item({ id: "c", status: "missing" }), item({ id: "d", status: "off" })];
    expect(summarize(items)).toMatchObject({ ready: 1, unchecked: 1, missing: 1, off: 1, attention: 1, total: 4 });
    expect(summarize(items, { b: { outcome: "failed" } })).toMatchObject({ unchecked: 0, blocked: 1, attention: 2 });
  });

  it("lists only the testable entries and the names still to set", () => {
    expect(testable([item({ test: null }), item({ id: "x" })]).map((i) => i.id)).toEqual(["x"]);
    expect(needsList(item({ needs: ["SMTP_HOST", "SMTP_PASSWORD"] }))).toBe("SMTP_HOST\nSMTP_PASSWORD");
  });
});

describe("browser geocoder test", () => {
  const reply = (ok, body, status = 200) => async () => ({ ok, status, json: async () => body });

  it("passes only when the town search returns a result", async () => {
    let t = 0;
    const now = () => (t += 30);
    expect((await testGeocoder(reply(true, [{ nom: "Lyon" }]), { now })).outcome).toBe("passed");
    expect((await testGeocoder(reply(true, { features: [{}] }), { now })).outcome).toBe("passed"); // the address service
    const none = await testGeocoder(async (url) => ({ ok: true, status: 200, json: async () => (url.includes("geo.api") ? [] : { features: [] }) }), { now });
    expect(none.outcome).toBe("failed");
    expect(none.detail).toContain("without a result");
  });

  it("asks the official communes list first and only asks the address service when it fails", async () => {
    const calls = [];
    const fetchImpl = async (url) => { calls.push(url); return { ok: true, status: 200, json: async () => [{ nom: "Lyon" }] }; };
    const out = await testGeocoder(fetchImpl);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("geo.api.gouv.fr/communes");
    expect(out.detail).toContain("official communes list");

    calls.length = 0;
    const fallback = async (url) => {
      calls.push(url);
      if (url.includes("geo.api")) throw new TypeError("Failed to fetch");
      return { ok: true, status: 200, json: async () => ({ features: [{}] }) };
    };
    const degraded = await testGeocoder(fallback);
    expect(calls).toHaveLength(2);
    expect(degraded.outcome).toBe("passed");
    expect(degraded.detail).toContain("works through its fallback"); // working, and honest about which service answered
  });

  it("reports an HTTP error and a blocked request, never a silent success", async () => {
    const http = await testGeocoder(reply(false, {}, 504));
    expect(http.outcome).toBe("failed");
    expect(http.detail).toContain("504");
    const down = await testGeocoder(async () => { throw new TypeError("Failed to fetch"); });
    expect(down.outcome).toBe("failed");
    expect(down.detail).toContain("unreachable");
  });

  it("gives up after the timeout", async () => {
    const hang = (url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
    const out = await testGeocoder(hang, { timeoutMs: 10 });
    expect(out.outcome).toBe("failed");
    expect(out.detail).toContain("no answer");
  });
});
