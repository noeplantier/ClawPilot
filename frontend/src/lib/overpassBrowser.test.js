import { fetchOverpass } from "@/lib/overpassBrowser";

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
const EP = ["https://a.example/api/interpreter", "https://b.example/api/interpreter"];

test("the first server that answers wins, and the query is sent as a form field", async () => {
  const calls = [];
  const fetchFn = (url, init) => { calls.push([url, init.body.get("data")]); return url.includes("a.example") ? Promise.resolve({ ok: false, status: 504 }) : ok({ elements: [{ id: 1 }] }); };
  expect(await fetchOverpass("[out:json];", EP, { fetchFn })).toEqual({ elements: [{ id: 1 }] });
  expect(calls).toEqual([[EP[0], "[out:json];"], [EP[1], "[out:json];"]]);
});

test("when every server fails the error names each one, and a hung server is aborted", async () => {
  const fetchFn = (url, init) => (url.includes("a.example")
    ? new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(Object.assign(new Error("x"), { name: "AbortError" }))))
    : ok({ nope: true }));
  await expect(fetchOverpass("q", EP, { fetchFn, timeoutMs: 10 })).rejects.toMatchObject({
    failures: ["a.example: timeout", "b.example: not an Overpass answer"],
  });
});

test("a network error is reported as unreachable", async () => {
  await expect(fetchOverpass("q", [EP[0]], { fetchFn: () => Promise.reject(new TypeError("Failed to fetch")) })).rejects.toThrow("a.example: unreachable");
});

test("a slow server is hedged by the next one and the first valid answer wins, the loser being aborted", async () => {
  let aborted = false;
  const fetchFn = (url, init) => (url.includes("a.example")
    ? new Promise((_, reject) => init.signal.addEventListener("abort", () => { aborted = true; reject(Object.assign(new Error("x"), { name: "AbortError" })); }))
    : ok({ elements: [{ id: 2 }] }));
  expect(await fetchOverpass("q", EP, { fetchFn, hedgeMs: 15 })).toEqual({ elements: [{ id: 2 }] });
  expect(aborted).toBe(true); // nobody waits for the silent server
});

test("a server that refuses us with 403 frees its place for the next one at once", async () => {
  const calls = [];
  const fetchFn = (url) => { calls.push(url); return url.includes("a.example") ? Promise.resolve({ ok: false, status: 403 }) : ok({ elements: [] }); };
  expect(await fetchOverpass("q", EP, { fetchFn, hedgeMs: 5000 })).toEqual({ elements: [] });
  expect(calls).toEqual(EP); // no 5 s hedge delay was needed
});

test("the application's own relay is asked first, and is named 'relay' in the failures", async () => {
  const calls = [];
  const fetchFn = (url) => { calls.push(url); return Promise.resolve({ ok: false, status: 502 }); };
  await expect(fetchOverpass("q", [EP[0]], { fetchFn, relay: true })).rejects.toMatchObject({
    failures: ["relay: HTTP 502", "a.example: HTTP 502"],
  });
  expect(calls).toEqual(["/relay/overpass", EP[0]]);
});

test("an answer cut short by the server (HTTP 200 with a runtime error) is not an answer", async () => {
  const fetchFn = (url) => ok(url.includes("a.example") ? { elements: [], remark: "runtime error: Query timed out" } : { elements: [{ id: 3 }] });
  expect(await fetchOverpass("q", EP, { fetchFn })).toEqual({ elements: [{ id: 3 }] });
});

test("never more than three servers are asked at once", async () => {
  let now = 0; let max = 0;
  const fetchFn = (url, init) => {
    now += 1; max = Math.max(max, now);
    return new Promise((_, reject) => init.signal.addEventListener("abort", () => { now -= 1; reject(Object.assign(new Error("x"), { name: "AbortError" })); }));
  };
  const many = ["a", "b", "c", "d", "e"].map((h) => `https://${h}.example/i`);
  await expect(fetchOverpass("q", many, { fetchFn, hedgeMs: 5, timeoutMs: 60 })).rejects.toMatchObject({ failures: expect.any(Array) });
  expect(max).toBeLessThanOrEqual(3);
  expect(max).toBeGreaterThan(1);
});
