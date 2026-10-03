// Legal identity of the publisher. Public information only (it is what the national business register shows).
// Deliberately NOT here: social-security number, date of birth, identity documents, private phone number, and the
// home address (published in the RNE; the notices below point to it instead of copying it).
// Change `REVIEW_PENDING` to false once a legal adviser has validated the three pages: until then each page says so.

export const REVIEW_PENDING = true;

export const PUBLISHER = {
  product: "Plantiers - OutreachOS",
  company: "Plantiers - Software Engineering",
  legalForm: "Entrepreneur individuel (micro-entrepreneur)",
  owner: "Noé Plantier",
  publicationDirector: "Noé Plantier",
  siren: "941473332",
  ape: "6201Z",
  registerUrl: "https://data.inpi.fr/entreprises/941473332",
  website: "https://www.plantiers.com",
  email: "founder@plantiers.com",
  vat: null, // to complete: VAT number, or the "TVA non applicable, art. 293 B du CGI" mention if that is the regime
  activity:
    "Conseil et prestation de services en développement de sites web et d'applications mobiles, SEO/GEO et UX/UI design.",
};

// Hosting providers: to be confirmed against the contracts actually in force.
export const HOSTS = [
  { role: "Interface (frontend)", name: "Netlify, Inc.", address: "San Francisco, CA, États-Unis", url: "https://www.netlify.com" },
  { role: "API et base de données (backend)", name: "Render Services, Inc.", address: "San Francisco, CA, États-Unis", url: "https://render.com" },
];

export const SEO = {
  title: "Plantiers - OutreachOS | AI-powered lead generation for software agencies",
  description:
    "Detect companies that need digital solutions, qualify them, and run compliant outreach campaigns. Built by Plantiers - Software Engineering.",
};
