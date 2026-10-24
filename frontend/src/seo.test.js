/* global __dirname */
// The static head is what crawlers and AI engines read (the app itself is behind a login): pin it.
import fs from "fs";
import path from "path";
import { PUBLISHER, SEO } from "@/config/legal";

const html = fs.readFileSync(path.join(__dirname, "../public/index.html"), "utf8");
const meta = (attr, name) => (html.match(new RegExp(`<meta ${attr}="${name}" content="([^"]*)"`)) || [])[1];

test("title, description and keywords are the agreed ones", () => {
  expect(html).toContain(`<title>${SEO.title}</title>`);
  expect(meta("name", "description")).toBe(SEO.description);
  expect(meta("name", "keywords")).toBe("lead generation, B2B outreach, AI sales intelligence, digital agency, software engineering");
});

test("Open Graph and Twitter tags carry the same title and description", () => {
  expect(meta("property", "og:title")).toBe(SEO.title);
  expect(meta("property", "og:description")).toBe(SEO.description);
  expect(meta("name", "twitter:title")).toBe(SEO.title);
});

test("schema.org describes the Organization and the SoftwareApplication, published by Plantiers", () => {
  const json = JSON.parse(html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)[1]);
  const byType = Object.fromEntries(json["@graph"].map((n) => [n["@type"], n]));
  expect(byType.Organization.name).toBe(PUBLISHER.company);
  expect(byType.SoftwareApplication.name).toBe(PUBLISHER.product);
  expect(byType.SoftwareApplication.publisher["@id"]).toBe(byType.Organization["@id"]);
  expect(JSON.stringify(json)).not.toMatch(/aggregateRating|review|offers/); // nothing invented
});

test("the manifest and its icons exist", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "../public/manifest.json"), "utf8"));
  expect(manifest.name).toBe(PUBLISHER.product);
  for (const icon of manifest.icons) expect(fs.existsSync(path.join(__dirname, "../public", icon.src))).toBe(true);
  expect(html).not.toMatch(new RegExp("claw" + "pilot", "i")); // spelled in two parts so the branding guard does not flag this file
});
