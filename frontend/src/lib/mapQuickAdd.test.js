import { ATTEST_TEXT, describeAdded, quickAddBody } from "@/lib/mapQuickAdd";

const PLACE = {
  external_id: "node/1", name: "Chez Test", lat: 45.76, lon: 4.83, category: "restaurants", address: "1 rue X", postcode: "69002",
  city: "Lyon", phone: "+33 4 78 00 00 01", email: null, website: "https://chez-test.example", source_url: "https://www.openstreetmap.org/node/1",
  ignored: "not sent",
};

describe("quickAddBody", () => {
  it("sends only what the map published, leaves empty values out and always carries the attestation", () => {
    const body = quickAddBody(PLACE);
    expect(body.attestation).toBe(true);
    expect(body.place.email).toBeUndefined(); // null is "not published", never an invented value
    expect(body.place.ignored).toBeUndefined();
    expect(body.place.name).toBe("Chez Test");
    expect(body).toMatchObject({ approve: true, check_website: true });
  });

  it("only asks to read a website that exists, and approve is the person's explicit choice", () => {
    expect(quickAddBody({ ...PLACE, website: null }).check_website).toBe(false);
    expect(quickAddBody(PLACE, { checkWebsite: false }).check_website).toBe(false);
    expect(quickAddBody(PLACE, { approve: false }).approve).toBe(false);
  });

  it("states the attestation in words", () => {
    expect(ATTEST_TEXT).toContain("B2B prospecting");
    expect(ATTEST_TEXT).toContain("opt-outs");
  });
});

describe("describeAdded", () => {
  const base = { name: "Chez Test", created: true, in_crm: true, email: null, phone: null, email_found_on_site: false, website_checked: false };

  it("says what is known and what is not, and that nothing was sent", () => {
    const text = describeAdded(base).join(" ");
    expect(text).toContain("Chez Test is added");
    expect(text).toContain("in your CRM");
    expect(text).toContain("Nothing was sent");
    expect(text).toContain("E-mail: not known");
    expect(text).toContain("Phone: not known");
  });

  it("tells where an e-mail came from", () => {
    expect(describeAdded({ ...base, email: "a@b.example", email_found_on_site: true }).join(" ")).toContain("found on its own website");
    expect(describeAdded({ ...base, email: "a@b.example" }).join(" ")).toContain("published on the map");
  });

  it("never turns an unread website into 'no e-mail'", () => {
    const text = describeAdded(base, { siteAsked: true }).join(" ");
    expect(text).toContain("could not be read");
    expect(text).toContain("says nothing about its e-mail");
    expect(describeAdded({ ...base, website_checked: true }, { siteAsked: true }).join(" ")).toContain("Its website was read.");
  });

  it("distinguishes a duplicate and a prospect that still waits for review", () => {
    const text = describeAdded({ ...base, created: false, in_crm: false }).join(" ");
    expect(text).toContain("already one of your prospects");
    expect(text).toContain("review queue");
  });
});
