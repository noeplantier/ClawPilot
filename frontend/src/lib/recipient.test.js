import { addressOf, keyOf, looksLikeEmail, matchLead, sendBlock, suggestLeads } from "@/lib/recipient";

const LEADS = [
  { id: "l1", full_name: "Chez Marcel", company: "Marcel SARL", email: "Contact@Chez-Marcel.example", phone: "+33 4 78 00 00 01" },
  { id: "l2", full_name: "Pizzeria Il Forno", company: null, email: null, phone: "+33 4 78 00 00 02" },
  { id: "l3", full_name: "Café des Quais", company: "Quais SAS", email: "bonjour@cafe-quais.example", phone: null },
];

describe("matching what was typed to a lead", () => {
  it("ignores case and spaces for an e-mail, and punctuation for a phone number", () => {
    expect(matchLead(LEADS, "  contact@chez-marcel.EXAMPLE ", "email").id).toBe("l1");
    expect(matchLead(LEADS, "+33478000002", "whatsapp").id).toBe("l2");
    expect(keyOf("whatsapp", "+33 (4) 78-00.00.02")).toBe("33478000002");
  });
  it("never guesses: a similar address is not a match", () => {
    expect(matchLead(LEADS, "contact@chez-marcel.exampl", "email")).toBeNull();
    expect(matchLead(LEADS, "", "email")).toBeNull();
    expect(matchLead(null, "a@b.example", "email")).toBeNull();
  });
  it("only matches on the channel's own address", () => {
    expect(matchLead(LEADS, "bonjour@cafe-quais.example", "whatsapp")).toBeNull();
    expect(addressOf("email", LEADS[1])).toBe("");
  });
});

describe("suggestions while typing", () => {
  it("offers leads that have an address on this channel, by name, company or address, in the API's order", () => {
    expect(suggestLeads(LEADS, "", "email").map((l) => l.id)).toEqual(["l1", "l3"]); // l2 has no e-mail
    expect(suggestLeads(LEADS, "quais", "email").map((l) => l.id)).toEqual(["l3"]);
    expect(suggestLeads(LEADS, "MARCEL", "email").map((l) => l.id)).toEqual(["l1"]);
    expect(suggestLeads(LEADS, "", "whatsapp").map((l) => l.id)).toEqual(["l1", "l2"]);
  });
  it("cuts the list", () => {
    expect(suggestLeads(LEADS, "", "email", 1)).toHaveLength(1);
    expect(suggestLeads(undefined, "x", "email")).toEqual([]);
  });
});

describe("why a message cannot go", () => {
  it("explains an e-mail address that is not a lead, once a whole address is typed", () => {
    expect(sendBlock("email", "nobody@x.example", null, true)).toBe("not-a-lead");
    expect(sendBlock("email", "nobody@x.example", LEADS[0], true)).toBeNull();
    expect(sendBlock("email", "nob", null, true)).toBeNull(); // still typing
  });
  it("waits for the leads instead of refusing early, and leaves WhatsApp to the server", () => {
    expect(sendBlock("email", "nobody@x.example", null, false)).toBe("Loading your leads…");
    expect(sendBlock("whatsapp", "+33600000000", null, true)).toBeNull();
  });
  it("reads an address like a person would", () => {
    expect(["a@b.co", " a@b.co "].every(looksLikeEmail)).toBe(true);
    expect(["a@b", "a b@c.d", "@b.co", ""].some(looksLikeEmail)).toBe(false);
  });
});
