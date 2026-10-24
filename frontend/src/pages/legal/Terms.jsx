import LegalLayout from "@/pages/legal/LegalLayout";
import { PUBLISHER } from "@/config/legal";

export default function Terms() {
  return (
    <LegalLayout title="Conditions d'utilisation" updated="3 octobre 2026" testId="page-terms">
      <section>
        <h2>Objet</h2>
        <p>
          {PUBLISHER.product} est un outil de détection de prospects professionnels, de qualification, de rédaction de brouillons
          et d&apos;envoi encadré de messages, édité par {PUBLISHER.company}. L&apos;accès est réservé aux utilisateurs dont le compte a
          été créé ou autorisé par l&apos;éditeur.
        </p>
      </section>
      <section>
        <h2>Usage autorisé</h2>
        <ul>
          <li>Ne contacter que des prospects issus de sources dont vous avez le droit d&apos;utiliser les données, avec leur origine renseignée.</li>
          <li>Respecter la réglementation applicable à la prospection (RGPD, droit de la consommation et des communications électroniques) et les demandes d&apos;opposition.</li>
          <li>Ne pas contourner les garde-fous du service : validation humaine, limites d&apos;envoi, pause, kill switch, bac à sable.</li>
          <li>Interdits : CAPTCHA, connexion, paywall ou limite de débit contournés ; scraping ou automatisation de LinkedIn ; faux comptes, fausses identités ou faux numéros ; informations inventées sur un prospect ; WhatsApp sans opt-in traçable.</li>
        </ul>
      </section>
      <section>
        <h2>Responsabilités</h2>
        <p>
          L&apos;utilisateur reste responsable du contenu des messages qu&apos;il valide et de la légalité de sa prospection. Le service est
          fourni « en l&apos;état » : l&apos;éditeur ne garantit ni la remise des e-mails (une acceptation par un serveur n&apos;est pas une
          remise en boîte de réception), ni l&apos;exactitude des données issues de sources tierces. L&apos;éditeur peut suspendre un compte
          en cas d&apos;usage contraire aux présentes conditions.
        </p>
      </section>
      <section>
        <h2>Données personnelles</h2>
        <p>Voir la <a href="/privacy">politique de confidentialité</a>.</p>
      </section>
      <section>
        <h2>Droit applicable</h2>
        <p>Droit français. Contact : <a href={`mailto:${PUBLISHER.email}`}>{PUBLISHER.email}</a>. Clause de juridiction et conditions financières : à compléter.</p>
      </section>
    </LegalLayout>
  );
}
