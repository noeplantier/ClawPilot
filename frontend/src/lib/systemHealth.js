// Pure reading of the health report: what is OK, what is not, and what to do. No invented status.
export function checks(report) {
  if (!report) return [];
  const db = report.database;
  const mig = report.migrations;
  const where = { supabase_session_pooler: "Supabase (session pooler)", supabase_transaction_pooler: "Supabase (transaction pooler)", supabase_direct: "Supabase (direct)", render_postgres: "Render PostgreSQL", local: "local PostgreSQL" }[db.kind] || "PostgreSQL";
  const rows = [
    { key: "database", ok: db.ok, label: "Database", detail: db.ok ? `${where}, answered in ${db.latency_ms} ms` : `${where}: not reachable` },
    { key: "migrations", ok: mig.ok, label: "Migrations", detail: mig.ok ? `up to date (${mig.current})` : `database at ${mig.current || "unknown"}, code expects ${mig.head || "unknown"}` },
    { key: "cache", ok: report.cache.ok, label: "Source cache", detail: report.cache.ok ? `${report.cache.live_entries} live entr${report.cache.live_entries === 1 ? "y" : "ies"}` : "not readable" },
    { key: "workers", ok: true, label: "Background jobs", detail: report.workers.note },
  ];
  if (db.kind === "supabase_direct") rows[0] = { ...rows[0], ok: false, detail: `${where}: IPv6 only on the free plan; use the session pooler address unless this host has IPv6` };
  if (db.kind === "supabase_transaction_pooler") rows[0] = { ...rows[0], ok: false, detail: `${where}: prepared statements are not supported; use the session pooler (port 5432)` };
  return rows;
}

export function jobsLine(counts) {
  const entries = Object.entries(counts || {});
  if (entries.length === 0) return "No map search in the last 24 hours.";
  const total = entries.reduce((a, [, n]) => a + n, 0);
  return `${total} search${total === 1 ? "" : "es"} in 24 h: ` + entries.map(([k, n]) => `${n} ${k}`).join(", ") + ".";
}

export function probeLine(server) {
  if (server.ok) return `${server.host}: reachable (HTTP ${server.status}, ${server.ms} ms)`;
  if (server.status) return `${server.host}: answered HTTP ${server.status} (${server.ms} ms)`;
  return `${server.host}: ${server.error || "no answer"} (${server.ms} ms)`;
}

// Servers that failed recently are tried last for a few minutes: say so instead of hiding it.
export const coolingLine = (hosts) =>
  hosts && hosts.length > 0 ? `Failed recently, now tried last: ${hosts.join(", ")}.` : "";
