/* global KeyboardEvent, MouseEvent */
// The town search of the map: opens on focus and again after every choice, answers as you type, shows the counted leads of each town,
// and says so when the public services do not answer. fetch is mocked with recorded answers: no network.
import { act } from "react";
import { createRoot } from "react-dom/client";

import CityBox from "@/components/outreach/CityBox";

global.IS_REACT_ACT_ENVIRONMENT = true;

const commune = (nom, code, codes, lon, lat, population, dep) => ({ nom, code, codesPostaux: codes, centre: { type: "Point", coordinates: [lon, lat] }, population, departement: dep });
const LYON = commune("Lyon", "69123", ["69001", "69002"], 4.832, 45.758, 522250, { code: "69", nom: "Rhône" });
const LYONS = commune("Lyons-la-Forêt", "27375", ["27480"], 1.476, 49.399, 700, { code: "27", nom: "Eure" });
const NANTES = commune("Nantes", "44109", ["44000"], -1.553, 47.218, 320000, { code: "44", nom: "Loire-Atlantique" });
const STATS = [
  { city: "Lyon", key: "lyon", hot: 12, warm: 9, cold: 19, total: 40 },
  { city: "Villeurbanne", key: "villeurbanne", hot: 0, warm: 1, cold: 4, total: 5 },
];

let container;
let root;
let onPick;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);
const cell = (o, id) => (o.querySelector(`[data-testid="${id}"]`) || { textContent: "" }).textContent.trim();
// each suggestion as [name, detail, counts]
const rows = () => [...container.querySelectorAll('[role="option"]')].map((o) => [o.querySelector(".font-semibold").textContent, cell(o, "city-detail"), cell(o, "city-counts")]);
const names = () => rows().map((r) => r[0]);
const mount = async (props = {}) => {
  await act(async () => root.render(<CityBox stats={STATS} positions={new Map()} onPick={onPick} {...props} />));
};
const settle = async (ms = 200) => { await act(async () => { jest.advanceTimersByTime(ms); }); await act(async () => {}); };
const focus = async () => { await act(async () => { byId("map-goto").focus(); }); };
const type = async (value) => {
  await act(async () => {
    const el = byId("map-goto");
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const key = async (k) => { await act(async () => { byId("map-goto").dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true })); }); };
const answer = (json) => Promise.resolve({ ok: true, json: () => Promise.resolve(json) });

// What the two services answer, by text typed (only the communes whose name matches, as the real one does).
const routes = (url) => {
  if (url.startsWith("https://geo.api.gouv.fr/communes")) {
    const nom = decodeURIComponent((url.match(/nom=([^&]*)/) || [])[1] || "").toLowerCase();
    return answer([LYON, LYONS, NANTES].filter((c) => c.nom.toLowerCase().startsWith(nom)));
  }
  return Promise.reject(new Error(`unexpected ${url}`));
};

beforeEach(() => {
  jest.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  onPick = jest.fn();
  global.fetch = jest.fn(routes);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.useRealTimers();
});

describe("CityBox", () => {
  it("opens on focus with the towns where my hot leads are, before anything is typed and without any request", async () => {
    await mount();
    expect(byId("map-cities")).toBeNull();
    await focus();
    expect(byId("city-header").textContent).toBe("Your hottest towns");
    expect(rows()).toEqual([["Lyon", "from your leads", "12 hot · 40 leads"], ["Villeurbanne", "from your leads", "0 hot · 5 leads"]]);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("says what to type when no lead has a town yet", async () => {
    await mount({ stats: [] });
    await focus();
    expect(byId("city-header").textContent).toBe("Type a town or a postcode");
    expect(rows()).toEqual([]);
  });

  it("answers as you type from the official list and shows the counted leads next to each town", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toContain("geo.api.gouv.fr/communes?nom=ly");
    expect(rows()).toEqual([["Lyon (69)", "Rhône · 69001–69002", "12 hot · 40 leads"], ["Lyons-la-Forêt (27480)", "Eure", "no lead yet"]]);
    expect(container.querySelector('[data-tier="hot"]')).not.toBeNull();
    expect(container.querySelector('[data-tier="none"]').textContent).toBe("no lead yet");
  });

  it("opens again after a choice, on focus and on click, and keeps answering the second time", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    await act(async () => { byId("map-city-0").click(); });
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0]).toMatchObject({ name: "Lyon", lat: 45.758, lon: 4.832 });
    expect(byId("map-cities")).toBeNull();
    expect(byId("map-goto").value).toBe("Lyon (69)");
    await act(async () => { byId("map-goto").click(); }); // the same field, clicked again: the list is back
    expect(byId("map-cities")).not.toBeNull();
    expect(names()[0]).toBe("Lyon (69)"); // the town just chosen is listed again
    await type("nan"); // a second search in the same session
    await settle();
    expect(rows()).toEqual([["Nantes (44000)", "Loire-Atlantique", "no lead yet"]]);
  });

  it("remembers answers: the same text again costs no request", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    await type("lyo");
    await settle();
    const calls = global.fetch.mock.calls.length;
    await type("ly");
    await settle();
    expect(global.fetch.mock.calls.length).toBe(calls);
    expect(names()[0]).toBe("Lyon (69)");
  });

  it("narrows the list at once while the next answer is on its way", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    expect(names()).toHaveLength(2);
    await type("lyons"); // no timer advanced: the request is not even sent yet
    expect(names()).toEqual(["Lyons-la-Forêt (27480)"]);
    expect(byId("city-loading")).not.toBeNull();
    await settle();
    expect(byId("city-loading")).toBeNull();
  });

  it("sends one request when the text is typed quickly, not one per key", async () => {
    await mount();
    await focus();
    for (const v of ["l", "ly", "lyo", "lyon"]) { await type(v); await act(async () => { jest.advanceTimersByTime(40); }); }
    await settle();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toContain("nom=lyon");
  });

  it("works from the keyboard: arrows move, Enter chooses, Escape closes", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    await key("ArrowDown");
    await key("ArrowDown");
    expect(byId("map-city-1").getAttribute("aria-selected")).toBe("true");
    expect(byId("map-goto").getAttribute("aria-activedescendant")).toBe(byId("map-city-1").id);
    await key("ArrowUp");
    await key("Enter");
    expect(onPick.mock.calls[0][0].name).toBe("Lyon");
    await key("ArrowDown"); // reopens
    expect(byId("map-cities")).not.toBeNull();
    await key("Escape");
    expect(byId("map-cities")).toBeNull();
    expect(byId("map-goto").getAttribute("aria-expanded")).toBe("false");
  });

  it("Enter on a text with suggestions takes the best one", async () => {
    await mount();
    await focus();
    await type("lyon");
    await settle();
    await key("Enter");
    expect(onPick.mock.calls[0][0].name).toBe("Lyon");
  });

  it("falls back to the address service when the communes list fails", async () => {
    global.fetch = jest.fn((url) => (url.includes("geo.api.gouv.fr")
      ? Promise.reject(new Error("blocked"))
      : answer({ features: [{ geometry: { coordinates: [4.83, 45.76] }, properties: { city: "Lyon", postcode: "69001", citycode: "69123", context: "69, Rhône" } }] })));
    await mount();
    await focus();
    await type("lyon");
    await settle();
    expect(global.fetch.mock.calls.map((c) => c[0].split("?")[0])).toEqual(["https://geo.api.gouv.fr/communes", "https://api-adresse.data.gouv.fr/search/"]);
    expect(names()[0]).toBe("Lyon (69001)");
    expect(byId("city-error")).toBeNull();
  });

  it("says so when no service answers, and still offers the towns of my leads", async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error("offline")));
    await mount();
    await focus();
    await type("lyon");
    await settle();
    expect(byId("city-error").textContent).toContain("showing only the towns of your leads");
    expect(rows()).toEqual([["Lyon", "from your leads", "12 hot · 40 leads"]]);
    await type("zzz");
    await settle();
    expect(byId("city-error").textContent).toContain("did not answer");
  });

  it("says when no town matches, and is not fooled by a real empty answer", async () => {
    await mount();
    await focus();
    await type("zzz");
    await settle();
    expect(byId("city-none").textContent).toContain("No town matches");
    expect(byId("city-error")).toBeNull();
  });

  it("shows no count at all while the counts are not loaded", async () => {
    await mount({ stats: null });
    await focus();
    await type("ly");
    await settle();
    expect(names()).toHaveLength(2);
    expect(container.querySelector('[data-testid="city-counts"]')).toBeNull();
  });

  it("flies to a town of my leads from the position of my prospects there, without any lookup", async () => {
    await mount({ positions: new Map([["villeurbanne", { lat: 45.77, lon: 4.88 }]]) });
    await focus();
    await act(async () => { byId("map-city-1").click(); });
    expect(onPick.mock.calls[0][0]).toMatchObject({ name: "Villeurbanne", lat: 45.77, lon: 4.88 });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("looks a town of my leads up by name when none of my prospects there has a position", async () => {
    global.fetch = jest.fn(() => answer([commune("Lyon", "69123", ["69001"], 4.832, 45.758, 522250, { code: "69" })]));
    await mount({ positions: new Map() });
    await focus();
    await act(async () => { byId("map-city-0").click(); });
    await act(async () => {});
    expect(onPick.mock.calls[0][0]).toMatchObject({ name: "Lyon", lat: 45.758, lon: 4.832 }); // found by name, never guessed
  });

  it("says when a town of my leads cannot be located instead of moving the map somewhere", async () => {
    global.fetch = jest.fn(() => answer([]));
    await mount();
    await focus();
    await act(async () => { byId("map-city-1").click(); });
    await act(async () => {});
    expect(onPick).not.toHaveBeenCalled();
    expect(byId("city-note").textContent).toContain("Villeurbanne: no position found");
  });

  it("clears with the cross and reopens on the hottest towns", async () => {
    await mount();
    await focus();
    await type("ly");
    await settle();
    await act(async () => { byId("city-clear").click(); });
    expect(byId("map-goto").value).toBe("");
    expect(byId("city-header").textContent).toBe("Your hottest towns");
  });

  it("closes on a click outside and opens again on the next click in the field", async () => {
    await mount();
    await focus();
    expect(byId("map-cities")).not.toBeNull();
    await act(async () => { document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); });
    expect(byId("map-cities")).toBeNull();
    await act(async () => { byId("map-goto").click(); });
    expect(byId("map-cities")).not.toBeNull();
  });
});
