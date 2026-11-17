import { Link } from "react-router-dom";
import PageShell from "@/components/PageShell";
import OffersEditor from "@/components/outreach/OffersEditor";

// The three offers. Also step 1 of the batch dispatch (Outreach › Boîte de réception): this page stays for old links.
export default function Offer() {
  return (
    <PageShell testId="offer-page" kicker="Outreach" title="Offres"
      lead="Ce que vous vendez, en trois cas. Chaque brouillon parle de l'offre qui correspond à ce que l'on sait du site du prospect ; rien n'est envoyé sans votre validation."
      action={<Link to="/app/messages" className="btn-ghost">ENVOI PAR LOTS</Link>}>
      <OffersEditor />
    </PageShell>
  );
}
