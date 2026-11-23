import { CheckSquare, PuzzlePiece } from "@phosphor-icons/react";
import PageShell from "@/components/PageShell";
import HubTabs from "@/components/shell/HubTabs";
import { prospectsApi, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import ReviewQueue from "@/pages/ReviewQueue";
import ToEnrich from "@/pages/ToEnrich";
import AutoSelection from "@/components/hub/AutoSelection";

// « À traiter » : la file de relecture et la file « À enrichir » sur une seule page. Les deux compteurs viennent du serveur ;
// le raccourci clavier de la relecture et ses décisions (auditées) sont ceux de la file, inchangés.
export default function QualifyHub({ tab = "review" }) {
  const pending = useAsync(() => prospectsApi.queues("pending", { hideEmpty: true }), [], { key: "qualify:pending", intervalMs: LIVE_MS });
  const enrich = useAsync(() => prospectsApi.toEnrich({ limit: 1, offset: 0 }), [], { key: "qualify:to-enrich", intervalMs: LIVE_MS });
  const total = (d) => (d && typeof d.total === "number" ? d.total : undefined);
  const tabs = [
    { to: "/app/prospects/review", label: "À vérifier", testId: "hub-tab-review", icon: <CheckSquare size={15} aria-hidden="true" />, count: total(pending.data),
      hint: "Un prospect à la fois, le plus chaud d'abord, avec ses preuves. Approuver ne déclenche aucun envoi." },
    { to: "/app/prospects/to-enrich", label: "À enrichir", testId: "hub-tab-to-enrich", icon: <PuzzlePiece size={15} aria-hidden="true" />, count: total(enrich.data),
      hint: "Ce qui manque à chacun pour être qualifié : ils rejoignent la carte dès que tout est connu." },
  ];
  return (
    <PageShell testId="qualify-hub" kicker="Leads" title="À traiter"
      lead="Les prospects qui attendent une décision ou une information, dans une seule file.">
      <HubTabs tabs={tabs} label="Files de qualification" />
      {tab !== "to-enrich" && <AutoSelection onDecided={pending.reload} />}
      {tab === "to-enrich" ? <ToEnrich embedded /> : <ReviewQueue embedded />}
    </PageShell>
  );
}
