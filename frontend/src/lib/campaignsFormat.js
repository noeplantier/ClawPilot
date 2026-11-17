// Séquences : la catégorie, la progression réelle et la seule prochaine action de chaque campagne. Pur, sans I/O.
// Les compteurs viennent de l'API (GET /campaigns). « Accepté » veut dire accepté par le fournisseur d'envoi, jamais « livré ».

export const CATEGORIES = [
  { key: "draft", label: "Brouillons", hint: "Rien n'est parti : écrivez les étapes, ajoutez les destinataires, puis lancez." },
  { key: "running", label: "En cours", hint: "Les étapes partent sous les limites d'envoi, chaque message repasse les portes." },
  { key: "paused", label: "En pause", hint: "Plus rien ne part tant que vous ne reprenez pas." },
  { key: "completed", label: "Terminées", hint: "Toutes les étapes sont passées." },
];

export const STATUS_LABEL = { draft: "Brouillon", running: "En cours", paused: "En pause", completed: "Terminée" };

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Les catégories non vides, dans l'ordre du flux ; un statut inconnu n'est jamais rangé de force dans une autre.
export function groupCampaigns(list) {
  const rows = Array.isArray(list) ? list : [];
  return CATEGORIES.map((cat) => ({ ...cat, items: rows.filter((c) => c.status === cat.key) })).filter((g) => g.items.length > 0);
}

export const recipientsOf = (c) => (c && Array.isArray(c.lead_ids) ? c.lead_ids.length : 0);
export const stepsOf = (c) => (c && Array.isArray(c.steps) ? c.steps.length : 0);

// Messages acceptés par le fournisseur sur les messages prévus (destinataires × étapes). Sans destinataire ou sans étape, aucune
// proportion n'est inventée : pct vaut null et le texte dit ce qui manque.
export function progressOf(c) {
  const accepted = Number(c?.sent) || 0;
  const recipients = recipientsOf(c);
  const steps = stepsOf(c);
  if (!recipients) return { accepted, planned: 0, pct: null, text: "Aucun destinataire assigné" };
  if (!steps) return { accepted, planned: 0, pct: null, text: `${plural(recipients, "destinataire", "destinataires")}, aucune étape écrite` };
  const planned = recipients * steps;
  const pct = Math.min(100, Math.round((accepted / planned) * 100));
  return {
    accepted,
    planned,
    pct,
    text: `${accepted} accepté${accepted === 1 ? "" : "s"} par le fournisseur sur ${plural(planned, "message prévu", "messages prévus")}`,
  };
}

// Une seule action décisive par campagne, celle qui la fait avancer.
export function nextAction(c) {
  if (!c) return null;
  if (c.status === "draft") {
    if (!stepsOf(c)) return { key: "edit", label: "ÉCRIRE LA PREMIÈRE ÉTAPE" };
    if (!recipientsOf(c)) return { key: "open", label: "AJOUTER DES DESTINATAIRES" };
    return { key: "launch", label: "LANCER…" };
  }
  if (c.status === "running") return { key: "pause", label: "METTRE EN PAUSE" };
  if (c.status === "paused") return { key: "resume", label: "REPRENDRE…" };
  return { key: "open", label: "VOIR LE SUIVI" };
}

// Ce que l'opérateur confirme avant que quoi que ce soit parte : rien n'est caché derrière un bouton.
export function confirmLines(c, kind) {
  const recipients = recipientsOf(c);
  const lines = [
    kind === "resume"
      ? `Les étapes restantes de « ${c.name} » repartiront pour ${plural(recipients, "destinataire", "destinataires")}.`
      : `La première étape de « ${c.name} » part maintenant pour ${plural(recipients, "destinataire", "destinataires")}.`,
    "Un destinataire par message : aucune copie (CC/CCI) à plusieurs personnes.",
    "Chaque message repasse les portes au moment où il part : consentement et désinscriptions, rebonds, limites par jour et par heure, délai entre deux messages, pause du compte et arrêt d'urgence.",
    "« Accepté par le fournisseur » ne veut pas dire « livré » : la livraison, les rebonds et les réponses arrivent ensuite par le suivi.",
  ];
  return lines;
}
