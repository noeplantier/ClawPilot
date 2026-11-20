/* global require, __dirname */
// Motion stays cheap and optional (F1): an animation that never stops only moves transform or opacity (composited, no repaint
// on every frame), each one stops under "reduce motion", and every framer-motion animation follows that setting too.
const fs = require("fs");
const path = require("path");

const css = fs.readFileSync(path.join(__dirname, "index.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const layout = fs.readFileSync(path.join(__dirname, "components", "Layout.jsx"), "utf8");

// Every rule as { selector, body, media } (one level of @media nesting, which is all index.css uses).
function rules(text, media = null, base = 0) {
  const out = [];
  let i = 0; // `at` is the offset in the stylesheet: a later rule of equal weight wins, so a stop must come after its animation
  while (i < text.length) {
    const open = text.indexOf("{", i);
    if (open < 0) break;
    const head = text.slice(i, open).trim();
    let depth = 1;
    let j = open + 1;
    while (j < text.length && depth) {
      if (text[j] === "{") depth += 1;
      else if (text[j] === "}") depth -= 1;
      j += 1;
    }
    const body = text.slice(open + 1, j - 1);
    if (head.startsWith("@media")) out.push(...rules(body, head, base + open + 1));
    else out.push({ selector: head, body, media, at: base + open });
    i = j;
  }
  return out;
}

const all = rules(css);
const keyframes = Object.fromEntries(all.filter((r) => r.selector.startsWith("@keyframes")).map((r) => [r.selector.split(/\s+/)[1], r.body]));
const reduced = all.filter((r) => r.media && r.media.includes("prefers-reduced-motion"));
const infinite = all
  .filter((r) => !r.media && !r.selector.startsWith("@") && /animation:[^;]*\binfinite\b/.test(r.body))
  .map((r) => ({ selector: r.selector, at: r.at, name: r.body.match(/animation:\s*([\w-]+)/)[1] }));
const selectorList = (selector) => selector.split(",").map((s) => s.trim());
// A "reduce motion" rule that stops `selector`, written after the rule that animates it (otherwise the animation wins).
const stoppedAfter = (selector, at) =>
  reduced.some((r) => r.at > at && /animation:\s*none|display:\s*none/.test(r.body) && selectorList(r.selector).includes(selector));
// A loading spinner is the one loop kept under "reduce motion": it says that something is in progress.
const SPINNER = "spin-slow";

test("the stylesheet has infinite animations to check (the parser sees them)", () => {
  expect(infinite.map((a) => a.name)).toEqual(expect.arrayContaining(["pos-live", "pulse-dot", SPINNER]));
});

test("an animation that never stops only moves transform or opacity", () => {
  const costly = infinite.filter(({ name }) => /\b(box-shadow|width|height|top|left|right|bottom|margin|padding|filter)\s*:/.test(keyframes[name] || ""));
  expect(costly).toEqual([]);
});

test("every never-ending animation stops under prefers-reduced-motion (the spinner excepted)", () => {
  const missing = infinite.filter((a) => a.name !== SPINNER && !selectorList(a.selector).every((sel) => stoppedAfter(sel, a.at)));
  expect(missing).toEqual([]);
});

test("the page entrance is one short fade, with no delay, that leaves no transform behind", () => {
  const enter = all.find((r) => r.selector === ".page-enter" && !r.media);
  expect(enter.body).toMatch(/animation:\s*page-enter\s+var\(--dur-base\)\s+var\(--ease-out\)\s+backwards/);
  expect(enter.body).not.toMatch(/infinite|delay/);
  expect(keyframes["page-enter"]).toMatch(/opacity:\s*0/);
  expect(stoppedAfter(".page-enter", enter.at)).toBe(true);
});

test("framer-motion follows the system setting, and every screen enters through the frame", () => {
  expect(layout).toMatch(/<MotionConfig reducedMotion="user">/);
  expect(layout).toMatch(/<div key=\{pathname\} className="page-enter[^"]*">\s*<Outlet \/>/);
});
