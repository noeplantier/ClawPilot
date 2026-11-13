import { Robot, ShieldCheck } from "@phosphor-icons/react";
import PageShell from "@/components/PageShell";
import HubTabs from "@/components/shell/HubTabs";
import { mandatesApi, useAsync } from "@/lib/outreach";
import AutomationMax from "@/pages/AutomationMax";
import Agents from "@/pages/Agents";

// « Automatisations » : le mandat borné (Automatisation max) et les agents sur une seule page. L'interrupteur serveur
// (FEATURE_AUTOMATION_MAX) et l'autorisation d'un propriétaire restent les seules façons de faire agir un mandat.
export default function AutomationsHub({ tab = "max" }) {
  const overview = useAsync(() => mandatesApi.overview(), [], { key: "mandates:overview", intervalMs: 30000 });
  const mandates = overview.data && Array.isArray(overview.data.mandates) ? overview.data.mandates.length : undefined;
  const tabs = [
    { to: "/app/automation-max", label: "Mandat", testId: "hub-tab-max", icon: <ShieldCheck size={15} aria-hidden="true" />, count: mandates,
      hint: "Une autorisation explicite et bornée : le système envoie dans ces limites et s'arrête de lui-même." },
    { to: "/app/agents", label: "Agents", testId: "hub-tab-agents", icon: <Robot size={15} aria-hidden="true" />,
      hint: "Les tâches de fond supervisées par un opérateur." },
  ];
  return (
    <PageShell testId="automations-hub" kicker="Pilotage" title="Automatisations"
      lead="Ce qui agit sans vous, dans les limites que vous avez écrites, et ce que vous pouvez arrêter à tout instant.">
      <HubTabs tabs={tabs} label="Automatisations" />
      {tab === "agents" ? <Agents embedded /> : <AutomationMax embedded />}
    </PageShell>
  );
}
