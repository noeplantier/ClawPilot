// Navigation groups and sections of Plantiers OutreachOS. Pure: no React, no network.

export const NAV_GROUPS = [
  {
    id: "main",
    label: "MAIN",
    items: [
      { id: "dashboard", to: "/app/dashboard", label: "Dashboard", icon: "SquaresFour", testId: "nav-dashboard", legacyIds: ["nav-overview"] },
      { id: "map", to: "/app/map", label: "Live Prospect Map", icon: "MapTrifold", testId: "nav-map", legacyIds: ["nav-prospecting"], liveDot: true },
      { id: "leads", to: "/app/leads", label: "Leads", icon: "Users", testId: "nav-leads", matchPrefixes: ["/app/leads", "/app/prospects", "/app/sources"] },
      { id: "campaigns", to: "/app/launch", label: "Campaigns", icon: "PaperPlaneTilt", testId: "nav-campaigns", legacyIds: ["nav-outreach"], matchPrefixes: ["/app/campaigns", "/app/launch", "/app/messages", "/app/sending"] },
      { id: "analytics", to: "/app/analytics", label: "Analytics", icon: "TrendUp", testId: "nav-analytics" },
    ],
  },
  {
    id: "intelligence",
    label: "INTELLIGENCE",
    items: [
      { id: "drafts", to: "/app/drafts", label: "AI Draft Generator", icon: "Sparkle", testId: "nav-drafts", legacyIds: ["nav-batches"], matchPrefixes: ["/app/drafts", "/app/batches"] },
      { id: "agents", to: "/app/agents", label: "Automations", icon: "Cpu", testId: "nav-agents" },
      { id: "qualification", to: "/app/prospects/review", label: "Lead Qualification", icon: "ShieldCheck", testId: "nav-qualification", matchPrefixes: ["/app/prospects/review", "/app/prospects/to-enrich"], countKey: "pending_review" },
    ],
  },
  {
    id: "configuration",
    label: "CONFIGURATION",
    items: [
      { id: "offer", to: "/app/settings/offer", label: "Offer & Services", icon: "Briefcase", testId: "nav-offer" },
      { id: "integrations", to: "/app/settings?tab=integrations", label: "Integrations", icon: "PlugsConnected", testId: "nav-integrations" },
      { id: "settings", to: "/app/settings", label: "Settings", icon: "Gear", testId: "nav-settings", legacyIds: ["nav-control"] },
      { id: "system", to: "/app/system", label: "System Health", icon: "Heartbeat", testId: "nav-system", statusDot: true },
    ],
  },
];

// Preserved SECTIONS array for backward compatibility
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
    blurb: "Brouillons IA, campagne individuelle, séquences, boîte de réception, canaux.",
    tabs: [
      { to: "/app/drafts", label: "Brouillons IA", testId: "tab-drafts" },
      { to: "/app/launch", label: "Campagne individuelle", testId: "tab-launch" },
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
    if (query && !(path === p && kanban)) continue;
    if (!query && path === p && p === "/app/leads" && kanban) continue;
    if (p.length > bestLength) {
      best = tab;
      bestLength = p.length;
    }
  }
  return best;
}

// Find the active nav item across NAV_GROUPS
export function activeNavItem(pathname, search = "") {
  const path = pathOf(pathname);
  const searchParams = new URLSearchParams(search);
  const tabParam = searchParams.get("tab");

  let best = null;
  let bestScore = -1;

  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      const [itemPath, query] = item.to.split("?");
      const p = pathOf(itemPath);

      // Exact match with query param takes top priority (e.g., integrations tab)
      if (query && tabParam && query.includes(`tab=${tabParam}`) && path === p) {
        return item;
      }

      // Exact path match
      if (path === p) {
        if (!query) return item;
      }

      // Check configured matchPrefixes
      if (item.matchPrefixes) {
        for (const prefix of item.matchPrefixes) {
          const pref = pathOf(prefix);
          if ((path === pref || path.startsWith(`${pref}/`)) && pref.length > bestScore) {
            best = item;
            bestScore = pref.length;
          }
        }
      } else if (path.startsWith(`${p}/`) && p !== "/app" && p.length > bestScore) {
        best = item;
        bestScore = p.length;
      }
    }
  }
  return best;
}
