import LegalLayout from "@/pages/legal/LegalLayout";
import { HOSTS, PUBLISHER } from "@/config/legal";

export default function Legal() {
  return (
    <LegalLayout title="Mentions légales" updated="3 octobre 2026" testId="page-legal">
      <section>
        <h2>Éditeur</h2>
        <ul>
          <li>Service : {PUBLISHER.product}, édité par {PUBLISHER.company}.</li>
          <li>Forme juridique : {PUBLISHER.legalForm} — {PUBLISHER.owner}.</li>
          <li>SIREN : {PUBLISHER.siren} — code APE {PUBLISHER.ape}.</li>
          <li>
            Adresse de l&apos;établissement principal : telle qu&apos;inscrite au Registre national des entreprises,{" "}
            <a href={PUBLISHER.registerUrl} rel="noopener">{PUBLISHER.registerUrl.replace("https://", "")}</a>.
          </li>
          <li>Contact : <a href={`mailto:${PUBLISHER.email}`}>{PUBLISHER.email}</a> — site : <a href={PUBLISHER.website} rel="noopener">plantiers.com</a>.</li>
          <li>TVA : {PUBLISHER.vat || "à compléter (numéro de TVA, ou mention « TVA non applicable, art. 293 B du CGI » selon le régime)"}.</li>
          <li>Activité : {PUBLISHER.activity}</li>
        </ul>
      </section>
      <section>
        <h2>Directeur de la publication</h2>
        <p>{PUBLISHER.publicationDirector}.</p>
      </section>
      <section>
        <h2>Hébergement</h2>
        <ul>
          {HOSTS.map((h) => (
            <li key={h.name}>{h.role} : {h.name}, {h.address} — <a href={h.url} rel="noopener">{h.url.replace("https://", "")}</a>.</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Propriété intellectuelle</h2>
        <p>
          Le logiciel, les textes, la charte graphique et les marques « Plantiers » et « OutreachOS » sont la propriété de leur
          éditeur, sauf mention contraire. Toute reproduction non autorisée est interdite.
        </p>
      </section>
      <section>
        <h2>Signalement</h2>
        <p>Pour signaler un contenu ou un message abusif, ou exercer un droit sur vos données : <a href={`mailto:${PUBLISHER.email}`}>{PUBLISHER.email}</a>.</p>
      </section>
    </LegalLayout>
  );
}
