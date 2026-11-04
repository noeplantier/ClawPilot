// The history of what was launched, built only from what the server stored: map searches and list imports. Pure.
// There is no pause or resume: a search or an import runs to its end, so the page offers none and invents none.
const SEARCH_STATUS = { queued: "Queued", running: "Running", succeeded: "Finished", failed: "Failed" };

export function searchEntry(job) {
  const plural = job.result_count === 1 ? "" : "s";
  const detail = job.status === "succeeded" ? `${job.result_count} place${plural} saved` : job.status === "failed" ? "No result" : "In progress";
  return {
    key: `search:${job.id}`,
    kind: "Map search",
    title: `${job.category}`,
    status: SEARCH_STATUS[job.status] || job.status,
    tone: job.status === "failed" ? "danger" : job.status === "succeeded" ? "success" : "warn",
    detail,
    at: job.created_at,
    to: "/app/map",
  };
}

export function importEntry(batch) {
  const s = batch.summary || {};
  const created = Number.isFinite(s.prospects_created) ? s.prospects_created : null;
  return {
    key: `import:${batch.id}`,
    kind: "List import",
    title: batch.filename || batch.source_name,
    status: "Finished",
    tone: "success",
    detail: created === null ? `${batch.rows_total} rows` : `${batch.rows_total} rows, ${created} new prospect${created === 1 ? "" : "s"}`,
    at: batch.created_at,
    to: "/app/prospects",
  };
}

// Newest first; an entry without a date goes last rather than first.
export function mergeHistory(searches, imports, limit = 20) {
  const all = [...(searches || []).map(searchEntry), ...(imports || []).map(importEntry)];
  const time = (e) => (e.at ? Date.parse(e.at) || 0 : 0);
  return all.sort((a, b) => time(b) - time(a)).slice(0, limit);
}
