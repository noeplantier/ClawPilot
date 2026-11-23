// The six main sections of the application, and the screens each one holds. Pure: no React, no network.
//
// The sidebar shows exactly these six entries. The one you are in lists its screens right under it (there is no top bar any
// more): navigation inside a section, not a seventh, eighth… entry. The go-to palette (Ctrl+K) lists every screen of every
// section too. Every screen that exists belongs to one section; the tests check that none is left out, and every old path
// keeps working.
export const SECTIONS = [
  {
    id: "overview",
    label: "Vue d’ensemble",
    to: "/app/dashboard",
    icon: "SquaresFour",
    blurb: "Chiffres utiles, opportunités, alertes et activité récente.",
    tabs: [
      { to: "/app/dashboard", label: "Résumé", testId: "tab-dashboard" },
      { to: "/app/analytics", label: "Analytics", testId: "tab-analytics" },
    ],
  },
  {
    id: "prospecting",
    label: "Prospection",
    to: "/app/map",
    icon: "MapTrifold",
    blurb: "Carte, recherche, sources et découverte.",
    tabs: [
      { to: "/app/map", label: "Carte", testId: "tab-map" },
      { to: "/app/sources", label: "Sources", testId: "tab-sources" },
      { to: "/app/prospects/import", label: "Importer une liste", testId: "tab-import" },
    ],
  },
  {
    id: "leads",
    label: "Leads",
    to: "/app/leads",
    icon: "Users",
    blurb: "CRM (avec l'étape de chaque lead), prospects, et la file « À traiter » (à vérifier, à enrichir).",
    tabs: [
      { to: "/app/leads", label: "CRM", testId: "tab-crm" },
      { to: "/app/prospects", label: "Prospects", testId: "tab-prospects" },
      // « À vérifier » et « À enrichir » sont une seule page (deux onglets) : une seule entrée, les deux chemins y mènent.
      { to: "/app/prospects/review", label: "À traiter", testId: "tab-review", also: [{ to: "/app/prospects/to-enrich", label: "À enrichir" }] },
    ],
  },
  {
    id: "batches",
    label: "Batches",
    to: "/app/batches",
    icon: "Stack",
    blurb: "Lancements, progression et historique des recherches, imports et brouillons.",
    tabs: [{ to: "/app/batches", label: "Historique", testId: "tab-batches" }],
  },
  {
    id: "outreach",
    label: "Outreach",
    to: "/app/drafts",
    icon: "PaperPlaneTilt",
    blurb: "Brouillons IA, campagnes (par zone, individuelle, séquences), boîte de réception et offres, canaux.",
    tabs: [
      { to: "/app/drafts", label: "Brouillons IA", testId: "tab-drafts" },
      // Zone, individuelle, séquences : une seule page « Campagnes » (trois onglets et les graphiques en direct).
      { to: "/app/campaigns", label: "Campagnes", testId: "tab-campaigns", also: [{ to: "/app/journey", label: "Campagne par zone" }, { to: "/app/launch", label: "Campagne individuelle" }] },
      // The offers are step 1 of the batch dispatch, opened from the inbox: their page is part of it.
      { to: "/app/messages", label: "Boîte de réception", testId: "tab-messages", also: [{ to: "/app/settings/offer", label: "Offres" }], keywords: ["offre", "envoi par lots"] },
      { to: "/app/sending", label: "Canaux", testId: "tab-sending" },
    ],
  },
  {
    id: "control",
    label: "Pilotage",
    to: "/app/settings",
    icon: "Gear",
    blurb: "Intégrations, automatisations (agents et mandat), santé et réglages.",
    tabs: [
      { to: "/app/settings", label: "Intégrations et réglages", testId: "tab-settings" },
      // Agents et mandat « Automatisation max » : une seule page « Automatisations ».
      { to: "/app/automation-max", label: "Automatisations", testId: "tab-automation-max", also: [{ to: "/app/agents", label: "Agents" }], keywords: ["Automatisation max", "mandat"] },
      { to: "/app/system", label: "Santé", testId: "tab-system" },
    ],
  },
];

export const pathOf = (to) => String(to || "").split("?")[0].replace(/\/$/, "") || "/";

// The paths a tab answers for: its own, plus the screens merged into it (`also`), so an old link still lands on the right entry.
export const tabPaths = (tab) => [pathOf(tab.to), ...(tab.also || []).map((a) => pathOf(a.to))];

// The section a path belongs to. The longest matching tab wins (/app/prospects/review is "À vérifier", not "Prospects"),
// so a nested path never lands in the wrong section; null for a path outside the app.
export function sectionOf(pathname) {
  const path = pathOf(pathname);
  let best = null;
  let bestLength = -1;
  for (const section of SECTIONS) {
    for (const tab of section.tabs) {
      for (const p of tabPaths(tab)) {
        if ((path === p || path.startsWith(`${p}/`)) && p.length > bestLength) {
          best = section;
          bestLength = p.length;
        }
      }
    }
  }
  return best;
}

// The tab that is current: the longest tab path the address starts with (a prospect's sheet keeps "Prospects").
export function activeTab(section, pathname) {
  if (!section) return null;
  const path = pathOf(pathname);
  let best = null;
  let bestLength = -1;
  for (const tab of section.tabs) {
    for (const p of tabPaths(tab)) {
      if (!(path === p || path.startsWith(`${p}/`))) continue;
      if (p.length > bestLength) {
        best = tab;
        bestLength = p.length;
      }
    }
  }
  return best;
}

