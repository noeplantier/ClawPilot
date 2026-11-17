import { isComplete, offersBody, prefillFromOffer, usableOffers } from "@/lib/offersFormat";

const OK = { name: "Création de site", pitch: "Un site clair qui présente votre activité et vos horaires.", cta: "Un appel de 15 minutes ?" };

test("an offer is complete only within the server's limits", () => {
  expect(isComplete(OK)).toBe(true);
  expect(isComplete({ ...OK, pitch: "trop court" })).toBe(false);
  expect(isComplete(null)).toBe(false);
});

test("only the complete offers are saved, and the default must be one of them", () => {
  const forms = { creation: OK, seo_geo: { name: "", pitch: "", cta: "" } };
  expect(offersBody(forms, "creation", "fr")).toEqual({ ok: true, body: { language: "fr", default: "creation", offers: { creation: OK } } });
  expect(offersBody(forms, "seo_geo", "fr").ok).toBe(false);
});

test("a batch template carries the offer's own words and tokens, never a claim about the prospect", () => {
  const t = prefillFromOffer(OK, "fr");
  expect(t.subject).toBe("Création de site · {{company}}");
  expect(t.body).toBe(`Bonjour {{first_name}},\n\n${OK.pitch}\n\n${OK.cta}`);
  expect(t.body).not.toMatch(/I saw|j'ai vu|scaling|croissance/i);
  expect(prefillFromOffer({ ...OK, cta: "" })).toBeNull();
});

test("a batch can use only the configured offers", () => {
  const data = { cases: [{ kind: "creation", configured: true, offer: OK }, { kind: "seo_geo", configured: false, offer: null }] };
  expect(usableOffers(data).map((c) => c.kind)).toEqual(["creation"]);
  expect(usableOffers(null)).toEqual([]);
});
