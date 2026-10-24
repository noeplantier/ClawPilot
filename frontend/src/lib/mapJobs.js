// Map search as a persisted job: create it, poll it, read its places. Pure orchestration (the API and the clock are injected).
export const POLL_INTERVAL_MS = 1500;
export const POLL_MAX_MS = 120000;
const MAX_POLL_ERRORS = 3; // tolerate a hiccup on the way (a sleeping API instance waking up), not a dead connection

export const isFinished = (job) => job.status === "succeeded" || job.status === "failed";

export async function waitForJob(api, id, { sleep = (ms) => new Promise((r) => setTimeout(r, ms)), now = Date.now, onUpdate, intervalMs = POLL_INTERVAL_MS, maxMs = POLL_MAX_MS } = {}) {
  const started = now();
  let errors = 0;
  for (;;) {
    try {
      const job = await api.job(id);
      errors = 0;
      if (onUpdate) onUpdate(job);
      if (isFinished(job)) return job;
    } catch (e) {
      errors += 1;
      if (errors >= MAX_POLL_ERRORS || (e && e.response && e.response.status && e.response.status < 500)) throw e;
    }
    if (now() - started > maxMs) {
      const err = new Error("The search is taking too long. It keeps running: reopen the map in a minute to see its result.");
      err.timedOut = true;
      throw err;
    }
    await sleep(intervalMs);
  }
}

// One search, start to finish: the finished job and (when it succeeded) its places.
export async function runSearch(api, area, options = {}) {
  const created = await api.start(area);
  if (options.onUpdate) options.onUpdate(created);
  const job = isFinished(created) ? created : await waitForJob(api, created.id, options);
  return { job, places: job.status === "succeeded" ? await api.places(job.id) : null };
}

export function jobLine(job) {
  if (!job) return "";
  const seconds = job.duration_ms === null || job.duration_ms === undefined ? "" : ` in ${(job.duration_ms / 1000).toFixed(1)} s`;
  if (job.status === "queued") return "Search queued…";
  if (job.status === "running") return "Searching OpenStreetMap…";
  if (job.status === "failed") return `Search failed${seconds}.`;
  const from = job.source === "cache" ? "from the cache" : job.source === "overpass_browser" ? "through your browser" : "from OpenStreetMap";
  return `${job.result_count} place${job.result_count === 1 ? "" : "s"} saved ${from}${seconds}.`;
}

// A failed job offers the browser fallback only when the cause is the public servers (the API says so with `fallback`).
export const canRetryInBrowser = (job) => Boolean(job && job.status === "failed" && job.fallback);
