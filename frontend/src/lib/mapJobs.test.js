import { canRetryInBrowser, jobLine, runSearch, waitForJob } from "@/lib/mapJobs";

const job = (status, extra = {}) => ({ id: "j1", status, result_count: 0, duration_ms: null, source: "overpass", ...extra });
const noSleep = () => Promise.resolve();

test("polling follows the job until it is finished and reports each state", async () => {
  const states = [job("queued"), job("running"), job("succeeded", { result_count: 3, duration_ms: 1200 })];
  const api = { job: jest.fn(() => Promise.resolve(states.shift())) };
  const seen = [];
  const out = await waitForJob(api, "j1", { sleep: noSleep, onUpdate: (j) => seen.push(j.status) });
  expect(out.status).toBe("succeeded");
  expect(seen).toEqual(["queued", "running", "succeeded"]);
});

test("a failed job is returned as it is, with its explanation", async () => {
  const failed = job("failed", { error_code: "overpass_timeout", error: "did not answer" });
  const out = await waitForJob({ job: () => Promise.resolve(failed) }, "j1", { sleep: noSleep });
  expect(out).toBe(failed);
});

test("a couple of network hiccups are tolerated, a dead connection is not", async () => {
  let calls = 0;
  const flaky = { job: () => (++calls < 3 ? Promise.reject(new Error("net")) : Promise.resolve(job("succeeded"))) };
  expect((await waitForJob(flaky, "j1", { sleep: noSleep })).status).toBe("succeeded");
  await expect(waitForJob({ job: () => Promise.reject(new Error("net")) }, "j1", { sleep: noSleep })).rejects.toThrow("net");
  const refused = Object.assign(new Error("404"), { response: { status: 404 } });
  const once = jest.fn(() => Promise.reject(refused));
  await expect(waitForJob({ job: once }, "j1", { sleep: noSleep })).rejects.toBe(refused);
  expect(once).toHaveBeenCalledTimes(1); // a client error is not retried
});

test("polling gives up on the page, not on the job, after the maximum wait", async () => {
  let t = 0;
  const api = { job: () => Promise.resolve(job("running")) };
  await expect(waitForJob(api, "j1", { sleep: noSleep, now: () => (t += 50000), maxMs: 120000 })).rejects.toMatchObject({ timedOut: true });
});

test("runSearch starts the job, waits for it and then reads the places", async () => {
  const api = {
    start: jest.fn(() => Promise.resolve(job("queued"))),
    job: jest.fn(() => Promise.resolve(job("succeeded", { result_count: 1 }))),
    places: jest.fn(() => Promise.resolve({ places: [{ name: "A" }] })),
  };
  const out = await runSearch(api, { category: "bakeries" }, { sleep: noSleep });
  expect(api.start).toHaveBeenCalledWith({ category: "bakeries" });
  expect(out.places).toEqual({ places: [{ name: "A" }] });
  const failedApi = { start: () => Promise.resolve(job("failed")), places: jest.fn() };
  expect((await runSearch(failedApi, {})).places).toBeNull();
  expect(failedApi.places).not.toHaveBeenCalled();
});

test("texts say what happened and never claim a result that is not there", () => {
  expect(jobLine(job("queued"))).toBe("Search queued…");
  expect(jobLine(job("succeeded", { result_count: 1, duration_ms: 800 }))).toBe("1 place saved from OpenStreetMap in 0.8 s.");
  expect(jobLine(job("succeeded", { result_count: 0, source: "cache" }))).toBe("0 places saved from the cache.");
  expect(jobLine(job("succeeded", { result_count: 2, source: "overpass_browser" }))).toBe("2 places saved through your browser.");
  expect(canRetryInBrowser(job("failed", { fallback: { query: "q", endpoints: [] } }))).toBe(true);
  expect(canRetryInBrowser(job("failed"))).toBe(false);
  expect(canRetryInBrowser(job("succeeded", { fallback: {} }))).toBe(false);
});
