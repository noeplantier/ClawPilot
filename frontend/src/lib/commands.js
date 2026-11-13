// The "go to" palette (Ctrl or Cmd + K): every screen of the application and the actions that used to sit in the top bar.
// Pure: built from SECTIONS, so a screen added to a section is reachable here without touching anything else.
import { SECTIONS } from "@/lib/sections";

export const ACTIONS = [
  { id: "action-compose", label: "Composer IA", action: "compose", keywords: ["brouillon", "message", "ia", "écrire"] },
  { id: "action-usage", label: "Crédits et modèles d'outreach", action: "usage", keywords: ["utilisation", "limite", "modèle", "crédit"] },
  { id: "action-fold", label: "Replier ou déplier la navigation", action: "fold", keywords: ["menu", "barre latérale", "sidebar"] },
  { id: "action-logout", label: "Se déconnecter", action: "logout", keywords: ["quitter", "sortir", "logout"] },
];

// One command per screen (grouped by section, in the order of the sidebar), then the actions.
export function buildCommands(sections = SECTIONS) {
  const screens = sections.flatMap((section) =>
    section.tabs.flatMap((tab) => [
      {
        id: `go-${tab.testId}`,
        group: section.label,
        label: tab.label,
        to: tab.to,
        keywords: [section.label], // not the section's blurb: it names sibling screens, so every screen of a section would match them
      },
      // The screens merged into this tab stay reachable by their own name (an onglet of the same page).
      ...(tab.also || []).map((a) => ({ id: `go-${tab.testId}-${a.to.split("/").pop()}`, group: section.label, label: a.label, to: a.to, keywords: [section.label, tab.label] })),
    ]),
  );
  return [...screens, ...ACTIONS.map((a) => ({ ...a, group: "Actions" }))];
}

// The groups in order, each with its commands: what the palette renders.
export function groupCommands(commands) {
  const groups = [];
  for (const command of commands) {
    let group = groups.find((g) => g.label === command.group);
    if (!group) {
      group = { label: command.group, items: [] };
      groups.push(group);
    }
    group.items.push(command);
  }
  return groups;
}
