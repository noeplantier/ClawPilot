// Pure formatting of the merged pages (Campagnes, À traiter, Automatisations): no network, nothing invented.
// Every number comes from an API answer; a missing one is "—", never 0.
import { DASH, num, pct } from "@/lib/dashboardFormat";

// The live tiles of the « Campagnes » page, read from GET /dashboard/overview.
export function pulseTiles(d) {
  if (!d || !d.kpis || !d.limits) return [];
  const k = d.kpis;
  const l = d.limits;
  return [
    {
      key: "sent-today",
      label: "Envoyés aujourd'hui",
      value: `${num(l.sent_today)} / ${num(l.max_per_day)}`,
      hint: l.max_per_day > 0 ? `${num(l.remaining_today)} restant(s) dans la limite du jour` : "Aucune limite quotidienne configurée",
    },
    { key: "last-hour", label: "Dernière heure", value: `${num(l.sent_last_hour)} / ${num(l.max_per_hour)}`, hint: `Délai minimal ${num(l.min_delay_seconds)} s entre deux envois` },
    { key: "replies", label: "Réponses", value: num(k.replies), hint: `Taux de réponse ${pct(k.reply_rate)}` },
    { key: "bounces", label: "Rebonds", value: num(k.bounces), hint: `Taux ${pct(k.bounce_rate)}` },
    { key: "unsubscribed", label: "Désinscriptions", value: num(k.unsubscribed), hint: k.messages ? `sur ${k.messages} message(s)` : "Aucun message envoyé" },
  ];
}

// The bars of the campaigns, by messages sent: only campaigns that exist, sorted by what they really sent.
export function campaignBars(campaigns) {
  return (campaigns || [])
    .filter((c) => typeof c.sent === "number")
    .sort((a, b) => b.sent - a.sent)
    .slice(0, 6)
    .map((c) => ({ name: c.name, value: c.sent, fill: "var(--chart-sent, #9B74FA)" }));
}

// "Mis à jour à 14:03:12 · toutes les 10 s", or what is wrong with the refresh.
export function liveLine({ updatedAt, stale, intervalMs }) {
  if (!updatedAt) return "Chargement…";
  const at = updatedAt.toLocaleTimeString("fr-FR");
  return `${stale ? "Rafraîchissement en échec, dernières données affichées · " : "En direct · "}mis à jour à ${at} · toutes les ${Math.round(intervalMs / 1000)} s`;
}

// A count for a tab: the length of a list the API returned, else nothing (never an invented 0).
export const countOf = (data, pick = (d) => d) => {
  const list = data ? pick(data) : null;
  if (Array.isArray(list)) return list.length;
  if (list && typeof list.total === "number") return list.total;
  return undefined;
};

export { DASH };
