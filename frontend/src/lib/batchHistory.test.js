import { importEntry, mergeHistory, searchEntry } from "@/lib/batchHistory";

const search = (over = {}) => ({ id: "s1", status: "succeeded", category: "restaurants", result_count: 12, created_at: "2026-11-04T10:00:00Z", ...over });
const imp = (over = {}) => ({ id: "i1", filename: "lyon.csv", source_name: "import:ab", rows_total: 40, created_at: "2026-11-04T11:00:00Z", summary: { prospects_created: 31 }, ...over });

test("a finished search says how many places were saved, a failed one says it has no result, a running one says in progress", () => {
  expect(searchEntry(search())).toMatchObject({ status: "Finished", detail: "12 places saved", tone: "success" });
  expect(searchEntry(search({ result_count: 1 })).detail).toBe("1 place saved");
  expect(searchEntry(search({ status: "failed" }))).toMatchObject({ status: "Failed", detail: "No result", tone: "danger" });
  expect(searchEntry(search({ status: "running" }))).toMatchObject({ status: "Running", detail: "In progress", tone: "warn" });
});

test("an import reports the rows read and the prospects created, and never a figure the server did not give", () => {
  expect(importEntry(imp())).toMatchObject({ title: "lyon.csv", detail: "40 rows, 31 new prospects" });
  expect(importEntry(imp({ summary: {} })).detail).toBe("40 rows");
  expect(importEntry(imp({ filename: null })).title).toBe("import:ab");
});

test("the history is the stored searches and imports together, newest first, bounded", () => {
  const merged = mergeHistory([search({ id: "s1", created_at: "2026-11-04T10:00:00Z" })], [imp({ created_at: "2026-11-04T11:00:00Z" }), imp({ id: "i0", created_at: "2026-11-03T09:00:00Z" })]);
  expect(merged.map((e) => e.key)).toEqual(["import:i1", "search:s1", "import:i0"]);
  expect(mergeHistory(null, null)).toEqual([]);
  expect(mergeHistory(Array.from({ length: 30 }, (_, i) => search({ id: `s${i}` })), [], 5)).toHaveLength(5);
  expect(mergeHistory([search({ created_at: null, id: "undated" })], [imp()]).map((e) => e.key)).toEqual(["import:i1", "search:undated"]);
});
