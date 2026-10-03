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
