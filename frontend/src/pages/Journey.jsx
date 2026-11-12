import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { MapTrifold } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import PageShell from "@/components/PageShell";
import SetupChecklist from "@/components/journey/SetupChecklist";
import ZoneBlock from "@/components/journey/ZoneBlock";
import TemplateEditor from "@/components/journey/TemplateEditor";
import ApprovalPanel from "@/components/journey/ApprovalPanel";
import ProgressPanel from "@/components/journey/ProgressPanel";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import { canDecide, journeysApi, useAsync } from "@/lib/outreach";
import { journeyStatus, zoneFromSearch } from "@/lib/journeyFormat";
import { launchError } from "@/lib/launchFormat";
import { useJourney } from "@/lib/useJourney";
import { zoneSummary } from "@/lib/mapSearch";

// « Campagne par zone » : trois décisions (la zone, le brouillon, l'approbation), le système fait le reste.
// Cet écran n'envoie rien : approuver planifie, chaque message est revérifié au moment où il part.
export default function Journey() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id") || "";
  const zone = zoneFromSearch(params.toString());
  return (
    <PageShell
      testId="journey-page"
      kicker="outreach.zone"
      title="Campagne par zone"
      lead="Choisissez une zone sur la carte, relisez le brouillon, approuvez : le système planifie, revérifie chaque envoi et suit les réponses."
      action={<Link to="/app/map" className="btn-ghost" data-testid="journey-open-map"><MapTrifold size={14} /> CHOISIR UNE ZONE</Link>}
    >
      {id ? <Detail id={id} onBack={() => setParams({})} /> : zone ? <Start zone={zone} onCreated={(next) => setParams({ id: next })} /> : <Home onOpen={(next) => setParams({ id: next })} />}
    </PageShell>
  );
}

function Home({ onOpen }) {
  const list = useAsync(() => journeysApi.list(), [], { key: "journeys:list", intervalMs: 30000 });
  if (list.error && !list.data) return <ErrorBlock message={list.error} onRetry={list.reload} />;
  if (!list.data) return <LoadingBlock label="Chargement des campagnes…" />;
  if (list.data.length === 0) {
    return (
      <EmptyBlock title="Aucune campagne par zone pour l'instant" testId="journey-empty">
        Ouvrez la carte, cherchez dans une commune, puis « Continuer vers la campagne » : la zone recherchée devient celle de la campagne.
      </EmptyBlock>
    );
  }
  return (
    <ul className="divide-y divide-border rounded-2xl border border-border bg-card" data-testid="journey-list">
      {list.data.map((j) => (
        <li key={j.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <div className="font-medium truncate">{j.name}</div>
            <div className="text-xs text-soft">{zoneSummary(j.zone)}</div>
            <div className="mt-1 text-xs text-faint">{j.recipients} destinataire{j.recipients === 1 ? "" : "s"} · {j.planned} planifié{j.planned === 1 ? "" : "s"} · {j.sent} accepté{j.sent === 1 ? "" : "s"} par le serveur SMTP</div>
          </div>
          <div className="flex items-center gap-3"><span className="chip chip-ink">{journeyStatus(j.status)}</span><button className="btn-ghost" onClick={() => onOpen(j.id)} data-testid="journey-open">OUVRIR</button></div>
        </li>
      ))}
    </ul>
  );
}

// A zone arrived from the map: say what is needed once, then create the campaign (candidates only; nothing is approved or sent).
function Start({ zone, onCreated }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const navigate = useNavigate();
  const ready = useAsync(() => journeysApi.readiness(), [], { key: "journeys:readiness", intervalMs: 30000 });
  const [name, setName] = useState(zone.label ? `${zone.label} · ${zone.category}` : `Zone · ${zone.category}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const out = await journeysApi.create({ name: name.trim(), zone });
      toast.success(`${out.selected} établissement${out.selected === 1 ? "" : "s"} de la zone retenu${out.selected === 1 ? "" : "s"}, ${out.excluded} exclu${out.excluded === 1 ? "" : "s"}.`);
      onCreated(out.id);
    } catch (err) {
      setError(launchError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={create} className="space-y-6" data-testid="journey-start">
      <ZoneBlock zone={zone} coverage={null} />
      {ready.data && <SetupChecklist readiness={ready.data} />}
      {ready.error && !ready.data && <ErrorBlock message={ready.error} onRetry={ready.reload} />}
      <label className="block max-w-md text-sm">
        <span className="text-soft">Nom de la campagne</span>
        <input className="neo-input w-full" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required data-testid="journey-name" />
      </label>
      {error && <p role="alert" className="text-sm text-red-300" data-testid="journey-error">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <button className="btn-primary" disabled={busy || !decide} data-testid="journey-create">{busy ? "CRÉATION…" : "PRÉPARER LE BROUILLON"}</button>
        <button type="button" className="btn-ghost" onClick={() => navigate("/app/journey")}>ANNULER</button>
      </div>
      {!decide && <p className="text-sm text-soft">Seuls un propriétaire ou un administrateur peuvent créer une campagne.</p>}
    </form>
  );
}

function Detail({ id, onBack }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const j = useJourney(id);
  const { data: summary } = j.summary;
  if (j.summary.error && !summary) return <ErrorBlock message={j.summary.error} onRetry={j.summary.reload} />;
  if (!summary) return <LoadingBlock label="Chargement de la campagne…" />;
  const { campaign } = summary;
  return (
    <div className="space-y-6" data-testid="journey-detail">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="font-display text-xl font-bold" data-testid="journey-title">{campaign.name}</h2><span className="chip chip-ink">{journeyStatus(campaign.status)}</span></div>
        <button className="btn-ghost" onClick={onBack} data-testid="journey-back">TOUTES LES CAMPAGNES</button>
      </div>
      {j.error && <p role="alert" className="rounded-xl border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-300" data-testid="journey-error">{j.error}</p>}
      <SetupChecklist readiness={summary.readiness} />
      <ZoneBlock zone={summary.zone} coverage={summary.coverage} />
      <TemplateEditor template={summary.template} examples={summary.examples} decide={decide} busy={j.busy} onSave={j.saveTemplate} />
      <ApprovalPanel summary={summary} decide={decide} busy={j.busy} onApprove={j.approve} />
      {j.progress.data && <ProgressPanel progress={j.progress.data} decide={decide} busy={j.busy} onPause={j.pause} onResume={j.resume} onRevoke={j.revoke} />}
    </div>
  );
}
