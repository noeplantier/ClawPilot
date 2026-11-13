import { useState } from "react";
import { toast } from "sonner";
import { Check, Lightning, Sparkle } from "@phosphor-icons/react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, usageApi, useAsync } from "@/lib/outreach";
import { describeApiError } from "@/lib/outreachFormat";
import { costText, meter, messagesLeft } from "@/lib/creditsFormat";
import { ErrorBlock } from "@/components/outreach/States";

const BAR = { ok: "bg-brand-violet", warn: "bg-amber-400", danger: "bg-red-500" };

// « Utilisation » : the credits left in the session and today, and the outreach model that writes the AI drafts.
// Read from GET /usage/credits; an owner or an admin changes the model (PUT /usage/model). Nothing here costs anything.
export default function UsageDialog({ open, onOpenChange }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const state = useAsync(() => usageApi.credits(), [open], { key: "usage:credits", intervalMs: open ? 15000 : 0 });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const d = state.data;
  const choose = async (id) => {
    setBusy(id);
    setError(null);
    try {
      await usageApi.setModel(id);
      toast.success("Modèle d'outreach changé : il s'applique aux prochains messages.");
      state.reload();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy("");
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl border-border bg-card" data-testid="usage-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-black tracking-tight">Utilisation</DialogTitle>
          <DialogDescription className="text-soft">
            Les crédits plafonnent le travail de l&apos;IA : rien ne part chez le fournisseur au-delà. Un appel qui échoue ne coûte rien.
          </DialogDescription>
        </DialogHeader>
        {state.error && !d && <ErrorBlock message={state.error} onRetry={state.reload} />}
        {!d && !state.error && <p role="status" className="text-sm text-soft">Chargement…</p>}
        {d && (
          <div className="space-y-6">
            <section aria-label="Limites d'utilisation" className="space-y-4" data-testid="usage-windows">
              {d.windows.map((w) => {
                const m = meter(w);
                return (
                  <div key={w.key} data-testid={`usage-${w.key}`}>
                    <div className="flex items-baseline justify-between gap-2 text-sm">
                      <span className="font-semibold">{w.label}</span>
                      <span className="font-mono text-xs text-soft" data-testid={`usage-${w.key}-label`}>{m.label}</span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/[0.08]" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={m.pct} aria-label={`${w.label} : ${m.pct} % utilisés`}>
                      <div className={`h-full rounded-full ${BAR[m.tone]} transition-[width] duration-500`} style={{ width: `${m.pct}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-faint" data-testid={`usage-${w.key}-reset`}>{m.reset}</p>
                  </div>
                );
              })}
            </section>

            <section aria-label="Modèles d'outreach" className="space-y-2" data-testid="usage-models">
              <h3 className="font-display text-base font-bold">Modèle d&apos;outreach</h3>
              <ul className="space-y-2" role="radiogroup" aria-label="Modèle d'outreach">
                {d.models.map((m) => {
                  const active = d.model === m.id;
                  return (
                    <li key={m.id}>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={active}
                        disabled={!decide || Boolean(busy) || active}
                        onClick={() => choose(m.id)}
                        data-testid={`model-${m.id}`}
                        className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
                          active ? "border-brand-violet bg-brand-violet/10" : "border-border hover:border-white/20 hover:bg-white/[0.03]"
                        } disabled:cursor-default`}
                      >
                        <span className="mt-0.5 shrink-0 text-brand-lilac" aria-hidden="true">{m.uses_ai ? <Sparkle size={18} weight="duotone" /> : <Lightning size={18} weight="duotone" />}</span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold">{m.name}</span>
                            {m.default && <span className="chip chip-ink">recommandé</span>}
                          </span>
                          <span className="block text-sm text-soft">{m.tagline}</span>
                          <span className="mt-1 block font-mono text-[11px] text-faint">{costText(m)} · {messagesLeft(m, d.windows)}</span>
                        </span>
                        {active && <Check size={18} weight="bold" className="mt-0.5 shrink-0 text-brand-lilac" aria-label="Modèle actuel" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {!decide && <p className="text-xs text-soft">Seul un propriétaire ou un administrateur change le modèle.</p>}
              {error && <p role="alert" className="text-sm text-red-300" data-testid="usage-error">{error}</p>}
            </section>
            <p className="text-[11px] text-faint">Limites réglées sur le serveur : {d.settings.join(", ")}.</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
