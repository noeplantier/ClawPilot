import { glowPoint, installCardGlow } from "@/lib/cardGlow";

test("the light sits under the pointer, in the card's own coordinates", () => {
  expect(glowPoint({ left: 100, top: 50 }, 160.4, 90)).toEqual({ x: "60px", y: "40px" });
});

test("the hovered card receives the position; nothing is installed under reduced motion", () => {
  const card = document.createElement("div");
  card.className = "surface";
  card.getBoundingClientRect = () => ({ left: 10, top: 10 });
  const inner = document.createElement("span");
  card.appendChild(inner);
  document.body.appendChild(card);
  const off = installCardGlow(document, { matchMedia: () => ({ matches: false }) });
  inner.dispatchEvent(Object.assign(new Event("pointermove", { bubbles: true }), { clientX: 30, clientY: 25 }));
  expect(card.style.getPropertyValue("--mx")).toBe("20px");
  expect(card.style.getPropertyValue("--my")).toBe("15px");
  off();
  const offReduced = installCardGlow(document, { matchMedia: () => ({ matches: true }) });
  inner.dispatchEvent(Object.assign(new Event("pointermove", { bubbles: true }), { clientX: 90, clientY: 90 }));
  expect(card.style.getPropertyValue("--mx")).toBe("20px");
  offReduced();
  card.remove();
});
