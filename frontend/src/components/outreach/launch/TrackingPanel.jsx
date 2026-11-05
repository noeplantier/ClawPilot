import { useState } from "react";
import { launchApi, useAsync } from "@/lib/outreach";
import { DELIVERY_NOTE, formatSlot, progress, TRACKING_CHIP, TRACKING_ORDER } from "@/lib/launchFormat";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// Étape 6 : le suivi honnête. Planifié, accepté par SMTP, simulé, échec, réponse, opposition, rebond. « Livré » n'existe pas.
export default function TrackingPanel({ launchId, version, timezone }) {
  const [state, setState] = useState("");
  const list = useAsync(() => launchApi.tracking(launchId, { ...(state ? { state } : {}), limit: 50 }), [launchId, state, version], {
    key: `launch:${launchId}:tracking:${state}`,
    intervalMs: 10000,
  });
  const data = list.data;
  const counts = data ? data.counts : {};
  const bar = progress(counts);
  const keys = TRACKING_ORDER.filter((k) => counts[k]);
  return (
    <section className="surface p-5 space-y-4" data-testid="launch-tracking">
      <h2 className="font-display font-bold">6 · Suivi</h2>
      <p className="text-xs text-faint" data-testid="launch-delivery-note">{DELIVERY_NOTE}</p>
      {list.error && !data && <ErrorBlock message={list.error} onRetry={list.reload} />}
      {list.loading && !data && <LoadingBlock label="Chargement du suivi…" />}
      {data && keys.length === 0 && state === "" && (
        <EmptyBlock title="Rien n'est planifié" testId="launch-tracking-empty">Le suivi apparaît dès que des messages sont planifiés.</EmptyBlock>
      )}
      {bar && <div className="text-sm text-soft" data-testid="launch-progress">{bar.done} / {bar.total} traités ({bar.percent} %)</div>}
      {keys.length > 0 && (
        <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="État d'envoi">
          <button role="tab" aria-selected={state === ""} onClick={() => setState("")} data-testid="launch-track-all"
            className={`px-3 py-1 rounded-full text-xs border ${state === "" ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border"}`}>Tous · {data.total && state === "" ? data.total : Object.values(counts).reduce((n, v) => n + v, 0)}</button>
          {keys.map((k) => (
            <button key={k} role="tab" aria-selected={state === k} onClick={() => setState(k)} data-testid={`launch-track-${k}`}
              className={`px-3 py-1 rounded-full text-xs border ${state === k ? "bg-brand-violet text-white border-brand-violet" : "bg-card border-border"}`}>{data.labels[k]} · {counts[k]}</button>
          ))}
        </div>
      )}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-border border border-border rounded-md" data-testid="launch-track-list">
          {data.items.map((r) => (
            <li key={r.lead_id} className="p-3 flex flex-wrap items-center gap-3 text-sm" data-testid="launch-track-row">
              <div className="min-w-0 flex-1">
                <div className="font-display font-semibold truncate">{r.name}{r.city ? <span className="text-faint font-normal"> · {r.city}</span> : null}</div>
                <div className="text-xs text-faint font-mono truncate">{r.email}</div>
              </div>
              <span className={`chip ${TRACKING_CHIP[r.state] || "chip-ink"}`} data-testid="launch-track-state">{r.label}</span>
              {r.reason && <span className="text-xs text-soft">{r.reason}</span>}
              <time className="text-xs text-faint w-40 text-right" dateTime={r.dispatched_at || r.planned_at}>
                {r.dispatched_at ? `parti ${formatSlot(r.dispatched_at, timezone)}` : `prévu ${formatSlot(r.planned_at, timezone)}`}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
