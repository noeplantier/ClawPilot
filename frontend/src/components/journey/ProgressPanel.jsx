import { useState } from "react";
import { ArrowCounterClockwise, Pause, Play } from "@phosphor-icons/react";
import { progressLine, trackingRows } from "@/lib/journeyFormat";

// The compact follow-up: progression, what needs the person, replies, pause and resume. Honest states only: an accepted message is
// "accepted by the SMTP server", never "delivered".
export default function ProgressPanel({ progress, decide, busy, onPause, onResume, onRevoke }) {
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const rows = trackingRows(progress.states);
  return (
    <section aria-label="Suivi" className="rounded-2xl border border-border bg-card p-4 space-y-3" data-testid="journey-progress">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-bold">Suivi</h2>
        {decide && progress.total > 0 && (
          <div className="flex gap-2">
            {progress.paused ? (
              <button className="btn-ghost" onClick={onResume} disabled={busy === "resume" || !progress.approval_valid} data-testid="journey-resume"><Play size={14} /> REPRENDRE</button>
            ) : (
              <button className="btn-ghost" onClick={onPause} disabled={busy === "pause"} data-testid="journey-pause"><Pause size={14} /> METTRE EN PAUSE</button>
            )}
            {progress.approval_valid && !confirmRevoke && <button className="btn-ghost" onClick={() => setConfirmRevoke(true)} data-testid="journey-revoke-open"><ArrowCounterClockwise size={14} /> RETIRER L&apos;APPROBATION</button>}
          </div>
        )}
      </div>
      {confirmRevoke && (
        <div role="group" aria-label="Confirmer le retrait" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-400/40 bg-red-500/10 p-3 text-sm">
          <span>Les envois planifiés sont annulés ; ce qui est déjà parti ne peut pas être rappelé.</span>
          <button className="btn-primary" onClick={async () => { await onRevoke(); setConfirmRevoke(false); }} disabled={busy === "revoke"} data-testid="journey-revoke-confirm">RETIRER</button>
          <button className="btn-ghost" onClick={() => setConfirmRevoke(false)}>ANNULER</button>
        </div>
      )}
      <div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.percent ?? 0} aria-label="Progression de la campagne">
          <div className="h-full bg-brand-violet" style={{ width: `${progress.percent ?? 0}%` }} />
        </div>
        <p className="mt-1 text-sm text-soft" data-testid="progress-line" aria-live="polite">{progress.paused ? "En pause · " : ""}{progressLine(progress)}</p>
      </div>
      {rows.length > 0 && (
        <ul className="flex flex-wrap gap-2" data-testid="progress-states">
          {rows.map((r) => <li key={r.key} className="chip chip-ink" data-testid={`state-${r.key}`}>{r.count} · {r.label}</li>)}
        </ul>
      )}
      {progress.actions.length > 0 && (
        <div role="status" className="rounded-xl border border-amber-300/30 bg-amber-300/10 p-3 text-sm" data-testid="progress-actions">
          <div className="font-medium">Action requise</div>
          <ul className="mt-1 space-y-0.5">{progress.actions.map((a) => <li key={a.code}>{a.count} · {a.label}</li>)}</ul>
        </div>
      )}
    </section>
  );
}
