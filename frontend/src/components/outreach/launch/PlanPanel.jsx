import { useState } from "react";
import { toast } from "sonner";
import { CalendarCheck, Warning } from "@phosphor-icons/react";
import { canDecide, launchApi, useAsync } from "@/lib/outreach";
import { confirmText, exclusionLines, formatDay, isPlanChanged, launchError, PLAN_BUTTON, planButton, scheduleLine } from "@/lib/launchFormat";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// Étape 5 : ce que fera « Planifier les messages approuvés », calculé par le serveur à l'instant (jamais depuis ce qu'un écran
// affichait). Le bouton envoie le nombre lu : si le réel a changé, rien n'est écrit et le plan est relu.
export default function PlanPanel({ launchId, user, version, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [stale, setStale] = useState(0);
  const plan = useAsync(() => launchApi.plan(launchId), [launchId, version, stale], { key: `launch:${launchId}:plan`, intervalMs: 30000 });
  const p = plan.data;
  const button = planButton({ plan: p, canDecide: canDecide(user), busy });
  const exclusions = p ? exclusionLines(p.exclusions, p.exclusion_labels) : [];

  const schedule = async () => {
    setBusy(true);
    try {
      const out = await launchApi.schedule(launchId, p.sendable);
      toast.success(`${out.scheduled} message(s) planifié(s). Rien n'est parti : chaque envoi repasse les portes à son heure.`);
      setAsking(false);
      onChanged();
    } catch (e) {
      toast.error(launchError(e));
      if (isPlanChanged(e)) setStale((n) => n + 1);
      setAsking(false);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    setBusy(true);
    try {
      const out = await launchApi.cancel(launchId);
      toast.success(`${out.cancelled} message(s) annulé(s). La campagne est en pause ; ce qui est déjà parti ne se rappelle pas.`);
      onChanged();
    } catch (e) {
      toast.error(launchError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-5 space-y-4" data-testid="launch-plan">
      <div className="flex items-center gap-2">
        <CalendarCheck size={18} className="text-brand-lilac" />
        <h2 className="font-display font-bold">5 · Plan d&apos;envoi</h2>
      </div>
      {plan.error && !p && <ErrorBlock message={plan.error} onRetry={plan.reload} />}
      {plan.loading && !p && <LoadingBlock label="Calcul du plan…" />}
      {p && (
        <>
          <div className="flex flex-wrap items-end gap-6">
            <div>
              <div className="text-4xl font-black tracking-tighter" data-testid="launch-sendable">{p.sendable}</div>
              <div className="text-sm text-soft">message(s) réellement envoyable(s) sur {p.selected} destinataire(s)</div>
            </div>
            <div className="text-sm text-soft max-w-xl" data-testid="launch-schedule-line">
              {scheduleLine(p.schedule) || "Aucun créneau à afficher tant qu'aucun message n'est approuvé."}
            </div>
          </div>
          {p.schedule.days.length > 0 && (
            <ul className="flex flex-wrap gap-1.5 text-xs" data-testid="launch-days">
              {p.schedule.days.map((d) => (
                <li key={d.date} className="chip chip-ink">{formatDay(d.date, p.schedule.timezone)} · {d.count}</li>
              ))}
            </ul>
          )}
          {exclusions.length > 0 && (
            <div className="text-sm" data-testid="launch-exclusions">
              <div className="text-faint text-xs mb-1">Exclus du plan, par raison</div>
              <ul className="space-y-0.5">
                {exclusions.map((e) => <li key={e.code}><b>{e.count}</b> · {e.label}</li>)}
              </ul>
            </div>
          )}
          {p.blockers.map((b) => (
            <div key={b.code} className="text-sm flex items-start gap-2 text-brand-lilac" role="alert" data-testid="launch-blocker"><Warning size={16} className="shrink-0 mt-0.5" /> {b.label}</div>
          ))}
          {p.warnings.map((w) => (
            <div key={w.code} className="text-sm text-soft flex items-start gap-2" data-testid="launch-warning"><Warning size={16} className="shrink-0 mt-0.5" /> {w.label}</div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            {!asking && (
              <button className="btn-primary" disabled={button.disabled} onClick={() => setAsking(true)} data-testid="launch-schedule">
                {PLAN_BUTTON}
              </button>
            )}
            {button.disabled && <span className="text-xs text-faint" data-testid="launch-schedule-reason">{button.reason}</span>}
            {canDecide(user) && <button className="btn-ghost" onClick={cancel} disabled={busy} data-testid="launch-cancel">ANNULER LES MESSAGES NON PARTIS</button>}
          </div>
          {asking && (
            <div className="border border-border rounded-md p-4 space-y-3" role="alertdialog" aria-label="Confirmer la planification" data-testid="launch-confirm">
              <p className="text-sm" data-testid="launch-confirm-text">{confirmText(p)}</p>
              <div className="flex gap-2">
                <button className="btn-primary" onClick={schedule} disabled={busy} data-testid="launch-confirm-yes">CONFIRMER : PLANIFIER {p.sendable}</button>
                <button className="btn-ghost" onClick={() => setAsking(false)} disabled={busy} data-testid="launch-confirm-no">REVENIR</button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
