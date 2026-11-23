import { Crosshair, Envelope, ListNumbers } from "@phosphor-icons/react";
import PageShell from "@/components/PageShell";
import HubTabs from "@/components/shell/HubTabs";
import CampaignPulse from "@/components/hub/CampaignPulse";
import { journeysApi, launchApi, useAsync } from "@/lib/outreach";
import { api } from "@/lib/api";
import { countOf } from "@/lib/hubFormat";
import Journey from "@/pages/Journey";
import Launch from "@/pages/Launch";
import Campaigns from "@/pages/Campaigns";

const SCREENS = { journey: Journey, launch: Launch, campaigns: Campaigns };

// « Campagnes » : campagne par zone, campagne individuelle et séquences sur une seule page, sous les chiffres en direct.
// Chaque onglet garde son chemin (/app/journey, /app/launch, /app/campaigns) et son moteur : rien n'est envoyé par cette page.
export default function CampaignsHub({ tab = "campaigns" }) {
  const journeys = useAsync(() => journeysApi.list(), [], { key: "journeys:list", intervalMs: 30000 });
  const launches = useAsync(() => launchApi.list(), [], { key: "launch:list", intervalMs: 20000 });
  const sequences = useAsync(() => api.get("/campaigns").then((r) => r.data), [], { key: "campaigns", intervalMs: 15000 });
  const Screen = SCREENS[tab] || Campaigns;
  const tabs = [
    { to: "/app/journey", label: "Par zone", testId: "hub-tab-journey", icon: <Crosshair size={15} aria-hidden="true" />, count: countOf(journeys.data),
      hint: "Une zone de la carte, un brouillon relu, une approbation : le système planifie et revérifie chaque envoi." },
    { to: "/app/launch", label: "Individuelle", testId: "hub-tab-launch", icon: <Envelope size={15} aria-hidden="true" />, count: countOf(launches.data),
      hint: "Un message personnalisé et relu par destinataire, planifié puis envoyé un par un." },
    { to: "/app/campaigns", label: "Séquences", testId: "hub-tab-campaigns", icon: <ListNumbers size={15} aria-hidden="true" />, count: countOf(sequences.data),
      hint: "Des étapes successives, envoyées sous les limites d'envoi." },
  ];
  return (
    <PageShell testId="campaigns-hub" kicker="Outreach" title="Campagnes" width="max-w-6xl"
      lead="Toutes vos campagnes au même endroit, avec ce qui part réellement, en direct. Chaque envoi repasse toutes les portes au moment où il part.">
      <CampaignPulse />
      <HubTabs tabs={tabs} label="Types de campagne" />
      <Screen embedded />
    </PageShell>
  );
}
