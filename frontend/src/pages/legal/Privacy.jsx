import LegalLayout from "@/pages/legal/LegalLayout";
import { PUBLISHER } from "@/config/legal";

export default function Privacy() {
  const mail = <a href={`mailto:${PUBLISHER.email}`}>{PUBLISHER.email}</a>;
  return (
    <LegalLayout title="Politique de confidentialité" updated="3 octobre 2026" testId="page-privacy">
      <section>
        <h2>Responsable du traitement</h2>
        <p>
          {PUBLISHER.owner}, {PUBLISHER.company} (SIREN {PUBLISHER.siren}). Contact pour toute question ou demande relative aux données
          personnelles : {mail}. Aucun délégué à la protection des données n&apos;est désigné.
        </p>
      </section>
      <section>
        <h2>Deux catégories de personnes concernées</h2>
        <ul>
          <li><strong>Les utilisateurs</strong> du service : adresse e-mail, nom, organisation, mot de passe (stocké haché), journal des actions sensibles.</li>
          <li>
            <strong>Les prospects professionnels</strong> : nom et coordonnées professionnelles d&apos;une entreprise ou de son
            dirigeant, issus de sources autorisées et tracées (source, date, méthode), et signaux observables sur leur présence en
            ligne (site, page de réservation…), avec le score qui en découle et sa justification.
          </li>
        </ul>
      </section>
      <section>
        <h2>Finalités et bases légales</h2>
        <ul>
          <li>Fournir le service et sécuriser les comptes : exécution du contrat, intérêt légitime (sécurité).</li>
          <li>
            Prospection commerciale B2B par e-mail : intérêt légitime (art. 6.1.f du RGPD), limitée aux messages en rapport avec
            l&apos;activité professionnelle du destinataire, avec information sur l&apos;origine des données et droit d&apos;opposition à
            chaque message.
          </li>
          <li>Preuve du respect des oppositions, désinscriptions et du consentement WhatsApp : obligation légale et intérêt légitime.</li>
        </ul>
      </section>
      <section>
        <h2>Ce que le service ne fait pas</h2>
        <ul>
          <li>Il n&apos;invente aucune information sur un prospect : un message n&apos;affirme que des faits observés et tracés.</li>
          <li>Aucun message n&apos;est envoyé sans validation humaine, ni en dehors des limites et du mode bac à sable configurés.</li>
          <li>Aucun contournement de CAPTCHA, de connexion ou de limite, aucun scraping de LinkedIn, aucun envoi WhatsApp sans opt-in traçable.</li>
        </ul>
      </section>
      <section>
        <h2>Destinataires et transferts</h2>
        <p>
          Hébergeurs (voir les mentions légales), fournisseur de messagerie SMTP de l&apos;éditeur (à compléter : nom du fournisseur),
          et, lorsqu&apos;ils sont activés, SendGrid (e-mail) et Twilio (WhatsApp). Plusieurs de ces prestataires sont établis aux
          États-Unis : les garanties applicables (cadre de protection des données UE-États-Unis ou clauses contractuelles types) sont
          à confirmer par prestataire. Aucune donnée n&apos;est vendue.
        </p>
      </section>
      <section>
        <h2>Durées de conservation</h2>
        <ul>
          <li>Compte utilisateur : pendant la durée d&apos;utilisation du service, puis suppression sur demande.</li>
          <li>Prospects : au maximum 3 ans après le dernier contact (référence CNIL), supprimés sans délai sur demande.</li>
          <li>
            Après une désinscription ou une demande d&apos;effacement, seule une empreinte irréversible de l&apos;adresse est conservée,
            pour ne plus jamais la recontacter.
          </li>
          <li>Journaux d&apos;audit : durée à fixer par l&apos;éditeur (à compléter).</li>
        </ul>
      </section>
      <section>
        <h2>Vos droits</h2>
        <p>
          Accès, rectification, effacement, limitation, opposition (notamment à la prospection : un lien de désinscription figure
          dans chaque e-mail) et portabilité : écrivez à {mail}. L&apos;effacement d&apos;un prospect efface aussi ses messages, signaux
          et événements. Vous pouvez saisir la CNIL : <a href="https://www.cnil.fr/fr/plaintes" rel="noopener">cnil.fr/fr/plaintes</a>.
        </p>
      </section>
      <section>
        <h2>Cookies et stockage local</h2>
        <p>
          Le service n&apos;utilise ni cookie publicitaire ni outil de mesure d&apos;audience tiers. Un jeton de session est conservé dans
          le stockage local de votre navigateur, strictement nécessaire à la connexion. Les polices sont chargées depuis Google Fonts (aucune image tierce n&apos;est chargée).
        </p>
      </section>
    </LegalLayout>
  );
}
