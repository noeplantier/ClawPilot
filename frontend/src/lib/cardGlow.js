// The light that follows the pointer across a card (plantiers.com, Card `glow`): one listener for the whole page, which writes
// two CSS variables (--mx, --my) on the hovered `.surface`. No React state, no re-render; nothing at all under reduced motion.
export function glowPoint(rect, clientX, clientY) {
  return { x: `${Math.round(clientX - rect.left)}px`, y: `${Math.round(clientY - rect.top)}px` };
}

export function installCardGlow(doc = typeof document !== "undefined" ? document : null, win = typeof window !== "undefined" ? window : null) {
  if (!doc || !win) return () => {};
  const reduce = win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return () => {};
  const onMove = (e) => {
    const card = e.target && e.target.closest ? e.target.closest(".surface") : null;
    if (!card) return;
    const p = glowPoint(card.getBoundingClientRect(), e.clientX, e.clientY);
    card.style.setProperty("--mx", p.x);
    card.style.setProperty("--my", p.y);
  };
  doc.addEventListener("pointermove", onMove, { passive: true });
  return () => doc.removeEventListener("pointermove", onMove);
}
