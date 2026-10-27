import { EMPTY_FOCUS, leadLine, leadLink, mapLink, zoneLine } from "@/lib/focus";

test("a zone is described with the counts the server returned, singular or plural", () => {
  expect(zoneLine({ ready: 4, site: 3 })).toBe("4 hot leads with a phone and an e-mail, 3 with a website");
  expect(zoneLine({ ready: 1, site: 0 })).toBe("1 hot lead with a phone and an e-mail"); // no website: nothing is said about one
});

test("a zone opens the map on its town, whatever its spelling", () => {
  expect(mapLink({ city: "Saint-Étienne" })).toBe("/app/map?city=Saint-%C3%89tienne");
});

test("a prospect opens its review page and a CRM lead the CRM; the line says what a person still has to do", () => {
  expect(leadLink({ id: "p1", kind: "prospect" })).toBe("/app/prospects/p1");
  expect(leadLink({ id: "l1", kind: "lead" })).toBe("/app/leads");
  expect(leadLine({ name: "Chez Marcel", company: "Chez Marcel", city: "Lyon", review_status: "pending" })).toBe("Lyon · to review");
  expect(leadLine({ name: "Alice", company: "Table SAS", city: null, review_status: null })).toBe("Table SAS");
  expect(leadLine({ name: "X", company: null, city: null, review_status: "approved" })).toBe("approved");
});

test("an empty answer says why and what to do, never a made-up suggestion", () => {
  expect(EMPTY_FOCUS).toContain("phone and an e-mail");
});
