// Campaign suggestions as the API reports them: counted facts, hottest first. Pure helpers.
export const KIND_LABEL = { segment: "Segment", signal: "Signal", hot: "Hot contacts", new_leads: "New leads" };

export function readyLine(s) {
  if (s.eligible > 0) return `${s.eligible} of ${s.total} can join a campaign today`;
  return s.blocked_reason || "Nobody in this group can receive a message yet.";
}

export function createLabel(s, busy) {
  if (busy) return "CREATING…";
  return s.eligible > 0 ? `CREATE DRAFT · ${s.eligible}` : "NOT READY";
}

export function basisLine(basis) {
  if (!basis) return "";
  const part = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  return `Computed from ${part(basis.prospects, "prospect", "prospects")} and ${part(basis.leads, "CRM lead", "CRM leads")}.`;
}

export const emptyText = (basis) =>
  basis && basis.prospects + basis.leads === 0
    ? "No suggestion yet: they appear once you have prospects or leads that share a segment, a detected signal or a stage."
    : "No group of at least two people shares a segment or a signal yet. Suggestions appear on their own as your data grows.";
