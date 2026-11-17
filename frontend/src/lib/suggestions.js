// Campaign suggestions as the API reports them: counted facts, highest heat first. Pure helpers.
// « Hot » is reserved for an observed, sourced commercial intent: a suggestion ranked by heat says « score élevé », never « hot ».
export const KIND_LABEL = { segment: "Segment", signal: "Signal", hot: "Scores les plus élevés", new_leads: "Nouveaux leads" };

export function readyLine(s) {
  if (s.eligible > 0) return `${s.eligible} sur ${s.total} peuvent rejoindre une campagne aujourd'hui`;
  return s.blocked_reason || "Personne dans ce groupe ne peut encore recevoir de message.";
}

export function createLabel(s, busy) {
  if (busy) return "CRÉATION…";
  return s.eligible > 0 ? `CRÉER LE BROUILLON · ${s.eligible}` : "PAS ENCORE PRÊT";
}

export function highScoreLabel(n) {
  return `${n} score${n === 1 ? "" : "s"} élevé${n === 1 ? "" : "s"}`;
}

export function basisLine(basis) {
  if (!basis) return "";
  const part = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  return `Calculé à partir de ${part(basis.prospects, "prospect", "prospects")} et ${part(basis.leads, "lead du CRM", "leads du CRM")}.`;
}

export const emptyText = (basis) =>
  basis && basis.prospects + basis.leads === 0
    ? "Aucune suggestion pour l'instant : elles apparaissent dès que des prospects ou des leads partagent un segment, un signal détecté ou une étape."
    : "Aucun groupe d'au moins deux personnes ne partage encore un segment ou un signal. Les suggestions apparaissent d'elles-mêmes avec vos données.";
