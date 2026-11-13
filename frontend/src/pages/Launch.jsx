import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise, Plus, Robot } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, launchApi, useAsync } from "@/lib/outreach";
import { exclusionLines, groupExcluded, jobLine, launchError, stageMeta, STAGES } from "@/lib/launchFormat";
import { formatDateTime } from "@/lib/outreachFormat";
import ProviderPanel from "@/components/outreach/launch/ProviderPanel";
import ReviewList from "@/components/outreach/launch/ReviewList";
import PlanPanel from "@/components/outreach/launch/PlanPanel";
import TrackingPanel from "@/components/outreach/launch/TrackingPanel";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const MAX = 100;

// Campagne de messages individuels : 100 établissements distincts, un brouillon personnalisé et relu par destinataire, un plan d'envoi,
// un suivi honnête. Cet écran ne génère rien au rendu et n'envoie rien : chaque action est un bouton, chaque envoi passe les
// portes du serveur au moment où il part.
export default function Launch({ embedded = false }) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const id = params.get("id") || "";
  const decide = canDecide(user);
  const [version, setVersion] = useState(0);
  const refresh = () => setVersion((n) => n + 1);

  const gates = useAsync(() => launchApi.provider(), [version], { key: "launch:provider", intervalMs: 30000 });
  const list = useAsync(() => launchApi.list(), [version], { key: "launch:list", intervalMs: 20000 });

  return (
    <div className={embedded ? "space-y-6" : "p-6 md:p-10 space-y-6"} data-testid="launch-page">
      {!embedded && <div>
        <div className="mono-accent">// outreach.launch</div>
        <h1 className="text-4xl font-black tracking-tighter">Campagne individuelle</h1>
        <p className="text-soft mt-1 max-w-3xl">
          Jusqu&apos;à {MAX} établissements distincts, un message personnalisé et relu pour chacun, planifié puis envoyé un par un.
          Un message n&apos;est jamais copié à plusieurs destinataires, et rien ne part avant que vous ne le planifiiez.
        </p>
      </div>}
      {gates.error && !gates.data && <ErrorBlock message={gates.error} onRetry={gates.reload} />}
      {gates.data && <ProviderPanel gates={gates.data} />}
      {!id && <Home decide={decide} list={list} gates={gates.data} onOpen={(next) => setParams({ id: next })} onChanged={refresh} />}
      {id && <Campaign id={id} user={user} version={version} onChanged={refresh} onBack={() => setParams({})} gates={gates.data} />}
    </div>
  );
}

function Home({ decide, list, onOpen, onChanged }) {
  const [name, setName] = useState("Campagne individuelle");
  const [size, setSize] = useState(MAX);
  const [busy, setBusy] = useState(false);
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const out = await launchApi.create({ name: name.trim(), size: Number(size) });
      toast.success(`${out.selected} établissement(s) sélectionné(s) sur ${out.requested} demandé(s).`);
      onChanged();
      onOpen(out.launch.id);
    } catch (err) {
      toast.error(launchError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <section className="surface p-5 space-y-3" data-testid="launch-create">
        <h2 className="font-display font-bold">2 · Sélectionner les établissements</h2>
        <p className="text-sm text-soft">
          Seuls les prospects validés par une personne et qualifiés sont candidats. Les doublons (adresse, établissement), les personnes
          désinscrites, les rebonds, les réponses, les prospects déjà dans une autre campagne et les contacts non autorisés par le
          fournisseur sont écartés, avec la raison.
        </p>
        {decide ? (
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="block text-faint text-xs mb-1">Nom de la campagne</span>
              <input className="neo-input" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required data-testid="launch-name" />
            </label>
            <label className="text-sm">
              <span className="block text-faint text-xs mb-1">Nombre d&apos;établissements (max {MAX})</span>
              <input className="neo-input !w-28" type="number" min={1} max={MAX} value={size} onChange={(e) => setSize(e.target.value)} required data-testid="launch-size" />
            </label>
            <button className="btn-primary" disabled={busy || name.trim().length < 2} data-testid="launch-create-submit">
              <Plus size={14} /> {busy ? "SÉLECTION…" : `SÉLECTIONNER ${size || MAX} ÉTABLISSEMENTS`}
            </button>
          </form>
        ) : (
          <p className="text-sm text-faint">Seuls un propriétaire ou un administrateur peuvent créer une sélection.</p>
        )}
      </section>
      {list.error && !list.data && <ErrorBlock message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <LoadingBlock />}
      {list.data && list.data.length === 0 && (
        <EmptyBlock title="Aucune campagne individuelle" testId="launch-empty">
          Validez d&apos;abord des prospects dans <Link to="/app/prospects/review" className="underline text-brand-lilac">À vérifier</Link>, puis créez une sélection.
        </EmptyBlock>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="surface divide-y divide-border" data-testid="launch-list">
          {list.data.map((c) => (
            <li key={c.id}>
              <button className="w-full text-left flex flex-wrap items-center gap-3 p-4 hover:bg-white/[0.03]" onClick={() => onOpen(c.id)} data-testid="launch-item">
                <div className="min-w-0 flex-1">
                  <div className="font-display font-semibold truncate">{c.name}</div>
                  <div className="text-xs text-faint">{c.recipients} destinataire(s) · {c.planned} planifié(s) · {c.sent} accepté(s) · créée {formatDateTime(c.created_at)}</div>
                </div>
                <span className="chip chip-ink">{c.status}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Campaign({ id, user, version, onChanged, onBack }) {
  const decide = canDecide(user);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [created, setCreated] = useState(null);
  const overview = useAsync(() => launchApi.overview(id), [id, version], { key: `launch:${id}:overview`, intervalMs: 10000 });
  const o = overview.data;

  const topUp = async () => {
    setBusy(true);
    try {
      const out = await launchApi.topUp(id, MAX);
      setCreated(out);
      toast.success(`${out.selected} établissement(s) ajouté(s).`);
      onChanged();
    } catch (e) {
      toast.error(launchError(e));
    } finally {
      setBusy(false);
    }
  };
  const generate = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const out = await launchApi.generateDrafts(id);
      toast.success(out.started ? `Préparation lancée en arrière-plan pour ${out.missing} destinataire(s).` : out.already_running ? "Une préparation est déjà en cours." : "Aucun brouillon manquant.");
      onChanged();
    } catch (e) {
      setNotice(launchError(e));
    } finally {
      setBusy(false);
    }
  };

  if (overview.error && !o) return <ErrorBlock message={overview.error} onRetry={overview.reload} />;
  if (!o) return <LoadingBlock />;
  const stages = o.stages || {};
  const exclusions = exclusionLines(o.exclusions, o.exclusion_labels);
  const missing = stages.no_draft || 0;
  const jobs = jobLine(o.draft_jobs);
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-ghost" onClick={onBack} data-testid="launch-back">← TOUTES LES CAMPAGNES</button>
        <h2 className="font-display font-bold text-xl" data-testid="launch-title">{o.launch.name}</h2>
        <span className="chip chip-ink">{o.launch.status}</span>
      </div>
      <section className="surface p-5 space-y-3" data-testid="launch-selection">
        <h2 className="font-display font-bold">2 · Sélection</h2>
        <div className="text-sm text-soft"><b className="text-foreground" data-testid="launch-recipients">{o.launch.recipients}</b> destinataire(s) distinct(s).</div>
        <div className="flex flex-wrap gap-1.5" data-testid="launch-stage-counts">
          {STAGES.filter((s) => stages[s.key]).map((s) => (
            <span key={s.key} className={`chip ${stageMeta(s.key).chip}`} title={s.hint}>{s.label} · {stages[s.key]}</span>
          ))}
        </div>
        {exclusions.length > 0 && (
          <div className="text-sm" data-testid="launch-selection-exclusions">
            <div className="text-faint text-xs mb-1">Écartés depuis la sélection, par raison</div>
            <ul>{exclusions.map((e) => <li key={e.code}><b>{e.count}</b> · {e.label}</li>)}</ul>
          </div>
        )}
        {decide && o.launch.recipients < MAX && (
          <button className="btn-ghost" onClick={topUp} disabled={busy} data-testid="launch-topup">
            <ArrowsClockwise size={14} /> COMPLÉTER LA SÉLECTION JUSQU&apos;À {MAX}
          </button>
        )}
        {created && created.excluded.length > 0 && (
          <details className="text-sm" data-testid="launch-created-excluded">
            <summary className="cursor-pointer text-soft">{created.excluded.length} prospect(s) écarté(s) lors du dernier ajout</summary>
            <ul className="mt-2 space-y-2">
              {groupExcluded(created.excluded).map((g) => (
                <li key={g.code}><b>{g.items.length}</b> · {g.label}
                  <div className="text-xs text-faint">{g.items.slice(0, 8).map((i) => i.name).join(", ")}{g.items.length > 8 ? "…" : ""}</div>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
      <section className="surface p-5 space-y-3" data-testid="launch-drafts">
        <div className="flex items-center gap-2"><Robot size={18} className="text-brand-lilac" /><h2 className="font-display font-bold">3 · Brouillons individuels</h2></div>
        <p className="text-sm text-soft">
          Un brouillon par destinataire, écrit par l&apos;IA à partir de son nom, de son activité, de sa ville, de son site et des constats sourcés,
          autour de <Link to="/app/settings/offer" className="underline text-brand-lilac">votre offre</Link>. Rien n&apos;est inventé ; la préparation est
          mise en cache et ne se refait que si les données changent. Le brouillon est une proposition : vous l&apos;approuvez à l&apos;étape 4.
        </p>
        {jobs && <div className="text-xs text-faint" data-testid="launch-jobs">Préparation : {jobs}</div>}
        {notice && (
          <div className="text-sm text-brand-lilac" role="alert" data-testid="launch-drafts-notice">
            {notice} <Link to="/app/settings/offer" className="underline">Décrire mon offre</Link>
          </div>
        )}
        {decide && (
          <button className="btn-purple" onClick={generate} disabled={busy || missing === 0} data-testid="launch-generate">
            <Robot size={14} /> {missing ? `GÉNÉRER LES BROUILLONS MANQUANTS (${missing})` : "TOUS LES BROUILLONS SONT PRÊTS"}
          </button>
        )}
      </section>
      <ReviewList launchId={id} user={user} stages={stages} version={version} onChanged={onChanged} />
      <PlanPanel launchId={id} user={user} version={version} onChanged={onChanged} />
      <TrackingPanel launchId={id} version={version} timezone={o.gates.timezone} />
    </>
  );
}
