import { ACTIONS, buildCommands, groupCommands } from "@/lib/commands";
import { SECTIONS } from "@/lib/sections";

describe("the go-to palette replaces nothing that the top bar offered", () => {
  const commands = buildCommands();
  it("lists every screen of every section once, in the order of the sidebar", () => {
    const screens = commands.filter((c) => c.to);
    expect(screens.map((c) => c.to)).toEqual(SECTIONS.flatMap((s) => s.tabs.map((t) => t.to)));
    expect(new Set(commands.map((c) => c.id)).size).toBe(commands.length);
    expect(screens.every((c) => c.group && c.label)).toBe(true);
  });
  it("keeps the former top-bar action (the AI composer), the fold and the sign-out", () => {
    expect(commands.filter((c) => c.action).map((c) => c.action).sort()).toEqual(["compose", "fold", "logout"]);
    expect(ACTIONS.find((a) => a.action === "compose").label).toBe("Composer IA");
  });
  it("groups by section then actions, and a screen added to a section appears without further work", () => {
    expect(groupCommands(commands).map((g) => g.label)).toEqual([...SECTIONS.map((s) => s.label), "Actions"]);
    const extra = [{ id: "x", label: "Z", to: "/app/z", testId: "tab-z" }];
    const added = buildCommands([{ ...SECTIONS[0], tabs: [...SECTIONS[0].tabs, ...extra] }]);
    expect(added.some((c) => c.to === "/app/z")).toBe(true);
  });
  it("a screen is not found by the words that describe its siblings", () => {
    const crm = commands.find((c) => c.to === "/app/leads");
    expect(crm.keywords.join(" ")).not.toMatch(/enrichir/i); // "enrichir" must find « À enrichir », not the CRM
    expect(commands.find((c) => c.to === "/app/prospects/to-enrich").label).toBe("À enrichir");
  });
  it("reaches the two screens of the new journey", () => {
    expect(commands.some((c) => c.to === "/app/journey" && c.label === "Campagne par zone")).toBe(true);
    expect(commands.some((c) => c.to === "/app/automation-max")).toBe(true);
  });
});
