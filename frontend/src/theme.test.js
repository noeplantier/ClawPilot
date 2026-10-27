/* global require, __dirname */
// The look of the application is decided in one place (src/index.css and tailwind.config.js), as on plantiers.com.
// Screens use its tokens (text-soft, text-faint, text-foreground, bg-card, border-border, brand-*), never a colour of their own:
// a hard-coded light-theme colour on the dark canvas is unreadable. This keeps it that way.
const fs = require("fs");
const path = require("path");

const SRC = __dirname;
const sources = (dir = SRC) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) return sources(full);
    return /\.(jsx?|css)$/.test(e.name) && !/\.test\./.test(e.name) ? [full] : [];
  });
const jsx = () => sources().filter((f) => /\.jsx?$/.test(f));
const read = (f) => fs.readFileSync(f, "utf8");
const rel = (f) => path.relative(SRC, f);

test("no screen carries a colour of its own in a class name (the WhatsApp brand green excepted)", () => {
  const offenders = [];
  for (const f of jsx()) {
    const found = read(f).match(/\b(?:text|bg|border|ring|divide|from|to|via|accent)-\[#[0-9a-fA-F]{3,8}\](?:\/\d+)?/g) || [];
    found.filter((c) => c !== "text-[#25D366]").forEach((c) => offenders.push(`${rel(f)}: ${c}`));
  }
  expect(offenders).toEqual([]);
});

test("light-theme utilities that vanish or glare on the dark canvas are not used", () => {
  const offenders = [];
  for (const f of jsx()) {
    const code = read(f);
    (code.match(/\bbg-white(?![\w/[-])/g) || []).forEach((c) => offenders.push(`${rel(f)}: ${c} (use bg-card)`));
    (code.match(/\b(?:text|bg|border)-(?:slate|gray|zinc|neutral|stone)-\d+/g) || [])
      .filter((c) => c !== "text-slate-800") // dark text on the one light label over the map tiles
      .forEach((c) => offenders.push(`${rel(f)}: ${c}`));
  }
  expect(offenders).toEqual([]);
});

test("the fonts are the ones of plantiers.com, self-hosted, and no third-party stylesheet is loaded", () => {
  const html = read(path.join(SRC, "..", "public", "index.html"));
  expect(html).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
  const index = read(path.join(SRC, "index.js"));
  expect(index).toMatch(/@fontsource\/inter\/latin-400\.css/);
  expect(index).toMatch(/@fontsource\/jetbrains-mono\/latin-400\.css/);
  const css = read(path.join(SRC, "index.css"));
  expect(css).not.toMatch(/Chivo|IBM Plex/);
  expect(css).toMatch(/--void: #07060B/);
});

test("the Plantiers mark is the real logo of the site and is used by the shell and the sign-in pages", () => {
  expect(fs.existsSync(path.join(SRC, "assets", "logo-mark.png"))).toBe(true);
  const logo = read(path.join(SRC, "components", "Logo.jsx"));
  expect(logo).toMatch(/assets\/logo-mark\.png/);
  for (const f of ["components/Layout.jsx", "pages/Login.jsx", "pages/Register.jsx"]) expect(read(path.join(SRC, f))).toMatch(/Logo/);
  const publicDir = path.join(SRC, "..", "public");
  for (const f of ["favicon-32.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "og-image.jpg"]) {
    expect(fs.existsSync(path.join(publicDir, f))).toBe(true);
  }
  expect(read(path.join(publicDir, "index.html"))).toMatch(/theme-color" content="#07060B"/);
});
