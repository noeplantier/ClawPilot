import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { CaretLeft, CaretRight, CheckCircle, XCircle } from "@phosphor-icons/react";
import { canDecide, launchApi, useAsync } from "@/lib/outreach";
import { approvableIds, authorizationChip, hasBlocking, launchError, reviewResultText, siteState, stageMeta, STAGES } from "@/lib/launchFormat";
import { formatDateTime } from "@/lib/outreachFormat";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const PAGE = 25;

function Row({ item, checked, onToggle, selectable }) {
  const meta = stageMeta(item.stage);
  const auth = authorizationChip(item.authorization);
  const draft = item.draft;
  const site = siteState(item.evidence && item.evidence.site_state);
  const facts = (item.evidence && item.evidence.facts) || [];
  const source = item.evidence && item.evidence.source;
  return (
    <li className="p-4 space-y-2" data-testid="launch-row" data-stage={item.stage}>
      <div className="flex flex-wrap items-center gap-3">
        {selectable && (
          <input type="checkbox" checked={checked} onChange={() => onToggle(draft.id)} aria-label={`Sélectionner ${item.name}`} data-testid="launch-row-check" />
        )}
        <div className="min-w-0 flex-1">
          <Link to={`/app/prospects/${item.lead_id}`} className="font-display font-semibold hover:underline">
            {item.name}
            {item.city ? <span className="text-faint font-normal"> · {item.city}</span> : null}
          </Link>
          <div className="text-xs text-faint font-mono truncate" data-testid="launch-row-email">{item.email || "Aucune adresse"}</div>
        </div>
        <span className={`chip ${auth.chip}`} title={item.authorization.label} data-testid="launch-row-auth">{auth.label}</span>
        <span className={`chip ${meta.chip}`} data-testid="launch-row-stage">{meta.label}</span>
      </div>
      <div className="text-xs text-soft">{item.authorization.label}</div>
      {item.exclusion && <div className="text-sm text-brand-lilac" data-testid="launch-row-exclusion">{item.exclusion.label}</div>}
      {draft ? (
        <details className="text-sm" data-testid="launch-row-draft">
          <summary className="cursor-pointer text-soft">
            <b className="text-foreground" data-testid="launch-row-subject">{draft.subject}</b>
            {draft.auto ? <span className="chip chip-ink ml-2">IA</span> : null}
            {draft.edited ? <span className="chip chip-warn ml-2">Modifié à la main</span> : null}
            <span className="text-faint ml-2">{formatDateTime(draft.created_at)}</span>
          </summary>
          <pre className="mt-2 whitespace-pre-wrap break-words overflow-x-auto font-sans text-sm text-soft border border-border rounded-md p-3 bg-card" data-testid="launch-row-body">{draft.body}</pre>
        </details>
      ) : (
        <div className="text-sm text-soft" data-testid="launch-row-nodraft">
          Aucun brouillon.{item.draft_job ? ` Préparation : ${item.draft_job.status}${item.draft_job.error ? ` — ${item.draft_job.error}` : ""}.` : ""}
        </div>
      )}
      <div className="text-xs space-y-1" data-testid="launch-row-evidence">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-faint">Preuves utilisées :</span>
          <span className={`chip ${site.chip}`}>{site.label}</span>
          {source ? <span className="text-faint">source {source.name}, relevée le {formatDateTime(source.fetched_at)}</span> : <span className="text-faint">aucune source enregistrée</span>}
        </div>
        {facts.length > 0 ? (
          <ul className="list-disc pl-5 text-soft">
            {facts.map((f) => <li key={f}>{f}</li>)}
          </ul>
        ) : (
          <div className="text-faint">Aucun constat cité : le message n&apos;affirme rien de plus que le nom, la ville et l&apos;activité.</div>
        )}
      </div>
      {item.problems.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid="launch-row-problems">
          {item.problems.map((p) => (
            <span key={p.code} className={`chip ${p.blocking ? "chip-danger" : "chip-warn"}`}>{p.blocking ? "Bloque : " : "À savoir : "}{p.label}</span>
          ))}
        </div>
      )}
      {item.dispatch && <div className="text-xs text-faint">Envoi : {item.dispatch.status}{item.dispatch.reason ? ` (${item.dispatch.reason})` : ""}</div>}
    </li>
  );
}

// Étape 4 : la revue avant lancement. Un brouillon est relu, puis approuvé ; un point bloquant (variable non résolue, constat sans source,
// identité manquante…) empêche l'approbation, et le serveur le refuse aussi.
export default function ReviewList({ launchId, user, stages, version, onChanged }) {
  const [stage, setStage] = useState("to_review");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const list = useAsync(() => launchApi.review(launchId, { stage, offset: page * PAGE, limit: PAGE }), [launchId, stage, page, version], {
    key: `launch:${launchId}:review:${stage}:${page}`,
    intervalMs: 15000,
  });
  const items = list.data ? list.data.items : [];
  const total = list.data ? list.data.total : 0;
  const decide = canDecide(user);
  const approvable = approvableIds(items);
  const toggle = (id) => setSelected((s) => { const next = new Set(s); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const act = async (decision, ids) => {
    if (!ids.length) return;
    setBusy(true);
    try {
      const result = await launchApi.reviewDrafts(launchId, ids, decision);
      (result.refused ? toast.warning : toast.success)(reviewResultText(result, decision));
      setSelected(new Set());
      onChanged();
    } catch (e) {
      toast.error(launchError(e));
    } finally {
      setBusy(false);
    }
  };
  const chosen = [...selected].filter((id) => items.some((r) => r.draft && r.draft.id === id));
  return (
    <section className="surface p-5 space-y-4" data-testid="launch-review">
      <h2 className="font-display font-bold">4 · Revue avant lancement</h2>
      <p className="text-sm text-soft">Relisez destinataire, objet, corps et preuves. Approuver ne planifie rien et n&apos;envoie rien.</p>
      <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="Étape du destinataire">
        {STAGES.map((s) => (
          <button key={s.key} role="tab" aria-selected={stage === s.key} onClick={() => { setStage(s.key); setPage(0); setSelected(new Set()); }} data-testid={`launch-stage-${s.key}`}
            className={`px-3 py-1 rounded-full text-xs border transition-colors ${stage === s.key ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border hover:bg-white/[0.04]"}`} title={s.hint}>
            {s.label} · {(stages && stages[s.key]) || 0}
          </button>
        ))}
      </div>
      {decide && stage === "to_review" && items.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" data-testid="launch-bulk">
          <button className="btn-ghost" onClick={() => setSelected(new Set(approvable))} disabled={!approvable.length || busy} data-testid="launch-select-all">
            TOUT SÉLECTIONNER ({approvable.length} approuvables)
          </button>
          <button className="btn-purple" onClick={() => act("approve", chosen)} disabled={!chosen.length || busy} data-testid="launch-approve">
            <CheckCircle size={14} /> APPROUVER LA SÉLECTION ({chosen.length})
          </button>
          <button className="btn-ghost" onClick={() => act("reject", chosen)} disabled={!chosen.length || busy} data-testid="launch-reject">
            <XCircle size={14} /> REJETER
          </button>
          {items.some(hasBlocking) && <span className="text-xs text-faint">Les brouillons avec un point bloquant ne sont pas sélectionnables.</span>}
        </div>
      )}
      {list.error && !list.data && <ErrorBlock message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <LoadingBlock label="Chargement de la revue…" />}
      {list.data && items.length === 0 && (
        <EmptyBlock title="Personne à cette étape" testId="launch-review-empty">
          {stage === "no_draft" ? "Tous les destinataires ont un brouillon." : "Aucun destinataire n'est à cette étape pour l'instant."}
        </EmptyBlock>
      )}
      {items.length > 0 && (
        <ul className="divide-y divide-border border border-border rounded-md" data-testid="launch-review-list">
          {items.map((item) => (
            <Row key={item.lead_id} item={item} selectable={decide && stage === "to_review" && Boolean(item.draft) && !hasBlocking(item)} checked={item.draft ? selected.has(item.draft.id) : false} onToggle={toggle} />
          ))}
        </ul>
      )}
      {total > PAGE && (
        <div className="flex items-center gap-3 text-sm" role="navigation" aria-label="Pages de la revue">
          <button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}><CaretLeft size={14} /> PRÉCÉDENT</button>
          <span>Page {page + 1} / {Math.ceil(total / PAGE)} · {total} destinataires</span>
          <button className="btn-ghost" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>SUIVANT <CaretRight size={14} /></button>
        </div>
      )}
    </section>
  );
}
