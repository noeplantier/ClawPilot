// The six main sections of the application, and the screens each one holds. Pure: no React, no network.
//
// The sidebar shows exactly these six, flat. What used to be a tree of sub-items is the row of tabs at the top of the
// content (`SectionTabs`): navigation inside a section, not a seventh, eighth… entry of the sidebar. Every screen that
// exists belongs to one section; `routes.test` checks that none is left out, and every old path keeps working.
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
    blurb: "CRM, prospects qualifiés et Hot, fiches et file « À enrichir ».",
    tabs: [
      { to: "/app/leads", label: "CRM", testId: "tab-crm" },
      { to: "/app/leads?view=kanban", label: "Pipeline", testId: "tab-pipeline" },
      { to: "/app/prospects", label: "Prospects", testId: "tab-prospects" },
      { to: "/app/prospects/review", label: "À vérifier", testId: "tab-review" },
      { to: "/app/prospects/to-enrich", label: "À enrichir", testId: "tab-to-enrich" },
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
    blurb: "Brouillons IA, campagnes et séquences, boîte de réception, canaux.",
    tabs: [
      { to: "/app/drafts", label: "Brouillons IA", testId: "tab-drafts" },
      { to: "/app/campaigns", label: "Campagnes et séquences", testId: "tab-campaigns" },
      { to: "/app/messages", label: "Boîte de réception", testId: "tab-messages" },
      { to: "/app/sending", label: "Canaux", testId: "tab-sending" },
    ],
  },
  {
    id: "control",
    label: "Pilotage",
    to: "/app/settings",
    icon: "Gear",
    blurb: "Offre, intégrations, automatisations, santé et réglages.",
    tabs: [
      { to: "/app/settings/offer", label: "Offre", testId: "tab-offer" },
      { to: "/app/settings", label: "Intégrations et réglages", testId: "tab-settings" },
      { to: "/app/agents", label: "Automatisations", testId: "tab-agents" },
      { to: "/app/system", label: "Santé", testId: "tab-system" },
    ],
  },
];

export const pathOf = (to) => String(to || "").split("?")[0].replace(/\/$/, "") || "/";

// The section a path belongs to. The longest matching tab wins (/app/prospects/review is "À vérifier", not "Prospects"),
// so a nested path never lands in the wrong section; null for a path outside the app.
export function sectionOf(pathname) {
  const path = pathOf(pathname);
  let best = null;
  let bestLength = -1;
  for (const section of SECTIONS) {
    for (const tab of section.tabs) {
      const p = pathOf(tab.to);
      if ((path === p || path.startsWith(`${p}/`)) && p.length > bestLength) {
        best = section;
        bestLength = p.length;
      }
    }
  }
  return best;
}

// The tab that is current. /app/leads is "CRM" unless ?view=kanban asks for the pipeline; a prospect's sheet keeps "Prospects".
export function activeTab(section, pathname, search = "") {
  if (!section) return null;
  const path = pathOf(pathname);
  const kanban = new URLSearchParams(search).get("view") === "kanban";
  let best = null;
  let bestLength = -1;
  for (const tab of section.tabs) {
    const [tabPath, query] = tab.to.split("?");
    const p = pathOf(tabPath);
    if (!(path === p || path.startsWith(`${p}/`))) continue;
    if (query && !(path === p && kanban)) continue; // a tab with a query matches only that query
    if (!query && path === p && p === "/app/leads" && kanban) continue; // the CRM tab yields to the pipeline
    if (p.length > bestLength) {
      best = tab;
      bestLength = p.length;
    }
  }
  return best;
}

