/* global require, __dirname */
// The product is the prospecting side of plantiers.com: its tokens must be the ones of the site. src/design/plantiers-reference.json holds
// the values read (read-only) from the site's own source; this checks that our stylesheet and Tailwind config carry exactly those.
const fs = require("fs");
const path = require("path");
const ref = require("./design/plantiers-reference.json");

const css = fs.readFileSync(path.join(__dirname, "index.css"), "utf8");
const tailwind = fs.readFileSync(path.join(__dirname, "..", "tailwind.config.js"), "utf8");
const variable = (name) => (css.match(new RegExp(`--${name}:\\s*([^;]+);`)) || [])[1]?.trim();
const rule = (selector) => {
  const start = css.indexOf(`${selector} {`);
  return start < 0 ? "" : css.slice(start, css.indexOf("}", start));
};

test("the canvas, surfaces, accent and leaf are the colours of the site", () => {
  expect(variable("void")).toBe(ref.void.DEFAULT);
  expect(variable("void-elevated")).toBe(ref.void.elevated);
  expect(variable("void-surface")).toBe(ref.void.surface);
  expect(variable("brand-violet")).toBe(ref.brand["500"]);
  expect(variable("brand-lilac").split(" ")[0]).toBe(ref.brand["300"]);
  expect(variable("brand-400")).toBe(ref.brand["400"]);
  expect(variable("leaf")).toBe(ref.leaf["400"]);
  for (const hex of [ref.void.DEFAULT, ref.void.elevated, ref.void.surface, ref.leaf["400"], ref.leaf["500"]]) expect(tailwind.toUpperCase()).toContain(hex);
});

test("text opacities and glows follow the site's scale", () => {
  expect(variable("text-primary")).toBe(`rgba(255, 255, 255, ${ref.textOpacity.primary})`);
  expect(variable("text-secondary")).toBe(`rgba(255, 255, 255, ${ref.textOpacity.secondary})`);
  expect(variable("text-muted")).toBe(`rgba(255, 255, 255, ${ref.textOpacity.tertiary})`);
  expect(variable("glow")).toBe(ref.glow.brand);
  expect(variable("glow-soft")).toBe(ref.glow.brandSoft);
});

test("the typefaces are Inter and JetBrains Mono", () => {
  expect(variable("font-interface")).toMatch(new RegExp(`^'${ref.fonts.sans}'`));
  expect(variable("font-mono")).toMatch(new RegExp(`^'${ref.fonts.mono}'`));
});

test("the focus ring is brand-400, 2px, offset 2px, like the site's", () => {
  expect(css).toMatch(/:focus-visible\s*\{\s*outline:\s*2px solid var\(--brand-400\);\s*outline-offset:\s*2px;/);
});

test("the primary button is the site's: solid brand-500, light top edge and glow, lifts and lightens on hover, scales on press", () => {
  const base = rule(".btn-primary");
  expect(base).toContain("background: var(--brand-500)");
  expect(base).toContain(ref.button.primaryShadow);
  expect(base).toContain("min-height: 2.5rem");
  const hover = rule(".btn-primary:hover");
  expect(hover).toContain("background: var(--brand-400)");
  expect(hover).toContain("translateY(-2px)");
  expect(hover).toContain(ref.button.primaryHoverShadow);
  expect(css).toMatch(/\.btn-primary:active[^{]*\{\s*transform:\s*scale\(0\.97\)/);
});

test("motion respects prefers-reduced-motion: the lift and the press are switched off, and nothing loops on the map or the tables", () => {
  const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce) {"));
  expect(reduced).toContain(".btn-primary:hover, .btn-primary:active, .btn-ghost:active { transform: none; }");
  // Nothing that stays on the map loops (pins, clusters, popups pulse a few times, then rest). The only loops are the progress sweep
  // of a search in flight and the HUD dot beside it: they exist only while the request runs, and reduced motion stops them.
  const loops = (css.match(/\.map-[\w-]+[^{]*\{[^}]*animation:[^}]*infinite[^}]*\}/g) || []).map((rule) => rule.split("{")[0].trim());
  expect(loops.sort()).toEqual(['.map-hud-dot[data-state="scanning"]', ".map-scan::before"]);
  expect(reduced).toMatch(/\.map-scan::before[^}]*animation: none/);
});
