/* global __dirname */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import fs from "fs";
import path from "path";
import Legal from "@/pages/legal/Legal";
import Privacy from "@/pages/legal/Privacy";
import Terms from "@/pages/legal/Terms";
import { PUBLISHER } from "@/config/legal";

global.IS_REACT_ACT_ENVIRONMENT = true;

async function render(Page) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<MemoryRouter><Page /></MemoryRouter>));
  return container;
}

test("legal notice shows the publisher identity from the register, not private data", async () => {
  const c = await render(Legal);
  const text = c.textContent;
  expect(text).toContain("Plantiers - Software Engineering");
  expect(text).toContain(PUBLISHER.siren);
  expect(text).toContain("Directeur de la publication");
  expect(text).toContain("Hébergement");
  expect(text).toContain("founder@plantiers.com");
  expect(text).toContain("à compléter"); // VAT regime is not known: flagged, not invented
  expect(text).not.toMatch(/Jean Bourel|Plérin|Tours|\b\d{15}\b|0666/); // no home address, no social-security number, no phone
});

test("each page links to the others through the footer and says it is awaiting legal review", async () => {
  for (const Page of [Legal, Privacy, Terms]) {
    const c = await render(Page);
    expect(c.querySelector('[data-testid="footer-legal"]').getAttribute("href")).toBe("/legal");
    expect(c.querySelector('[data-testid="footer-privacy"]').getAttribute("href")).toBe("/privacy");
    expect(c.querySelector('[data-testid="footer-terms"]').getAttribute("href")).toBe("/terms");
    expect(c.querySelector('[data-testid="footer-site"]').getAttribute("href")).toBe("https://www.plantiers.com");
    expect(c.textContent).toContain("© Plantiers - Software Engineering");
    expect(c.querySelector('[data-testid="review-pending"]')).not.toBeNull();
  }
});

test("the privacy policy states the rights, the origin of data and the absence of invented facts", async () => {
  const text = (await render(Privacy)).textContent;
  for (const needle of ["intérêt légitime", "droit d", "CNIL", "n'invente aucune information", "validation humaine", "3 ans"]) {
    expect(text.toLowerCase()).toContain(needle.toLowerCase());
  }
});

test("no private identifier is committed in the legal configuration", () => {
  const cfg = fs.readFileSync(path.join(__dirname, "../../config/legal.js"), "utf8");
  expect(cfg).not.toMatch(/\b\d{15}\b|Bourel|0666/);
});
