import { ShieldCheck, Warning } from "@phosphor-icons/react";
import { gateChips, limitsLine, providerNotice, schedulerNotice } from "@/lib/launchFormat";

// Étape 1 : qui enverrait, ce qu'il interdit, et ce qui retient un message avant le réseau. Tout vient du serveur ; rien n'est
// présenté comme autorisé parce qu'un quota est disponible.
export default function ProviderPanel({ gates }) {
  const notice = providerNotice(gates);
  if (!notice) return null;
  const scheduler = schedulerNotice(gates.scheduler);
  return (
    <section className="surface p-5 space-y-3" data-testid="launch-provider">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={18} className="text-brand-lilac" />
        <h2 className="font-display font-bold">1 · Fournisseur et garde-fous</h2>
        <span className={`chip ${notice.chip}`} data-testid="launch-provider-chip">{notice.label}</span>
      </div>
      <p className="text-sm text-soft" data-testid="launch-provider-restriction">{notice.restriction}</p>
      <p className="text-sm text-soft">Un quota d&apos;envoi disponible ne vaut pas autorisation : seul le droit du destinataire à recevoir une campagne par ce fournisseur compte.</p>
      <div className="flex flex-wrap gap-1.5" data-testid="launch-gates">
        {gateChips(gates).map((c) => (
          <span key={c.key} className={`chip ${c.chip}`}>{c.label}</span>
        ))}
      </div>
      <div className="text-xs text-faint" data-testid="launch-limits">{limitsLine(gates)}</div>
      <div className={`text-xs flex items-start gap-2 ${scheduler.ok ? "text-soft" : "text-brand-lilac"}`} data-testid="launch-scheduler">
        {!scheduler.ok && <Warning size={14} className="shrink-0 mt-0.5" />} <span>{scheduler.text}</span>
      </div>
    </section>
  );
}
