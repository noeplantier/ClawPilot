import { useState } from "react";
import { toast } from "sonner";
import { journeysApi, useAsync } from "@/lib/outreach";
import { launchError, siteState } from "@/lib/launchFormat";

// What each status means, as the server decided it (the screen recomputes nothing).
const STATUS = {
  will_receive: { label: "Recevra le message", chip: "chip-success" },
  planned: { label: "Planifié", chip: "chip-ink" },
  held_back: { label: "Retenu", chip: "chip-warn" },
  excluded: { label: "Exclu", chip: "chip-ink" },
  removed: { label: "Retiré par vous", chip: "chip-danger" },
  sent: { label: "Parti", chip: "chip-ink" },
};
const ORDER = ["will_receive", "planned", "held_back", "excluded", "removed", "sent"];
const COUNT = {
  will_receive: ["recevra le message", "recevront le message"],
  planned: ["planifié", "planifiés"],
  held_back: ["retenu", "retenus"],
  excluded: ["exclu", "exclus"],
  removed: ["retiré par vous", "retirés par vous"],
  sent: ["parti", "partis"],
};
export const countLine = (counts) => ORDER.filter((k) => counts[k]).map((k) => `${counts[k]} ${COUNT[k][counts[k] === 1 ? 0 : 1]}`).join(" · ");

// Every recipient of the zone campaign: the message it would receive and its offer, or why it does not. A decider may take one
// out (it is not replaced, never picked again, its planned message is cancelled) or put it back while no approval is in force.
export default function RecipientList({ journeyId, stamp, decide, onChanged }) {
  const list = useAsync(() => journeysApi.recipients(journeyId), [journeyId, stamp], { key: `journey:${journeyId}:recipients`, intervalMs: 30000 });
  const [open, setOpen] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const act = async (leadId, fn, done) => {
    setBusy(leadId);
    setError("");
    try {
      await fn();
      toast.success(done);
      setRemoving(null);
      setReason("");
    } catch (e) {
      setError(launchError(e));
    } finally {
      setBusy("");
      list.reload();
      onChanged();
    }
  };

  const data = list.data;
  return (
    <section aria-label="Destinataires" className="rounded-2xl border border-border bg-card p-4 space-y-3" data-testid="journey-recipients">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-bold">Destinataires</h2>
        {data && (
          <p className="text-xs text-soft" data-testid="recipients-counts">
            {countLine(data.counts) || "Aucun destinataire"}
          </p>
        )}
      </div>
      {list.error && !data && <p role="alert" className="text-sm text-red-300" data-testid="recipients-error">{list.error}</p>}
      {!data && !list.error && <p className="text-sm text-soft" data-testid="recipients-loading">Chargement des destinataires…</p>}
      {error && <p role="alert" className="text-sm text-red-300" data-testid="recipient-action-error">{error}</p>}
      {data && data.items.length === 0 && <p className="text-sm text-soft" data-testid="recipients-empty">Aucun établissement n&apos;a été retenu dans cette zone.</p>}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-border" data-testid="recipients">
          {data.items.map((r) => {
            const status = STATUS[r.status] || { label: r.status, chip: "chip-ink" };
            const why = r.status === "removed" ? r.removed_reason : r.status === "held_back" ? r.problems.join(" ; ") : r.exclusion_label;
            return (
              <li key={r.lead_id} className="py-2 text-sm" data-testid="recipient" data-status={r.status}>
                <div className="flex flex-wrap items-center gap-2">
                  <b className="min-w-0 truncate">{r.name || "Prospect supprimé"}</b>
                  {r.city && <span className="text-faint">{r.city}</span>}
                  <span className={`chip ${status.chip}`}>{status.label}</span>
                  {r.message && <span className="text-xs text-faint" data-testid="recipient-offer">Offre : {r.message.offer_label}</span>}
                  <span className="ml-auto flex items-center gap-2">
                    {r.message && (
                      <button className="btn-ghost" onClick={() => setOpen(open === r.lead_id ? null : r.lead_id)} aria-expanded={open === r.lead_id} data-testid="recipient-preview">
                        {open === r.lead_id ? "MASQUER" : "VOIR LE MESSAGE"}
                      </button>
                    )}
                    {decide && r.can_remove && removing !== r.lead_id && (
                      <button className="btn-ghost" onClick={() => { setRemoving(r.lead_id); setReason(""); }} disabled={busy === r.lead_id} data-testid="recipient-remove">RETIRER</button>
                    )}
                    {decide && r.can_restore && (
                      <button className="btn-ghost" onClick={() => act(r.lead_id, () => journeysApi.restoreRecipient(journeyId, r.lead_id), `${r.name} réintégré : il recevra le message après approbation.`)} disabled={busy === r.lead_id} data-testid="recipient-restore">RÉINTÉGRER</button>
                    )}
                  </span>
                </div>
                {why && <p className="mt-0.5 text-xs text-soft" data-testid="recipient-why">{why}</p>}
                {r.status === "removed" && !r.can_restore && decide && (
                  <p className="mt-0.5 text-xs text-faint" data-testid="recipient-restore-hint">Une approbation est en vigueur : révoquez-la pour le réintégrer.</p>
                )}
                {removing === r.lead_id && (
                  <div role="group" aria-label={`Retirer ${r.name}`} className="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-brand-violet/50 bg-brand-violet/10 p-3" data-testid="recipient-remove-confirm">
                    <p className="text-sm max-w-md">
                      {r.name} ne recevra pas ce message{r.status === "planned" ? " : son envoi planifié est annulé" : ""}. Il n&apos;est pas remplacé et ne sera pas repris par un complément.
                    </p>
                    <input className="neo-input min-w-[12rem] flex-1" placeholder="Motif (facultatif)" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="recipient-remove-reason" />
                    <button className="btn-primary" onClick={() => act(r.lead_id, () => journeysApi.removeRecipient(journeyId, r.lead_id, reason.trim()), `${r.name} retiré de la campagne.`)} disabled={busy === r.lead_id} data-testid="recipient-remove-yes">
                      {busy === r.lead_id ? "RETRAIT…" : "CONFIRMER LE RETRAIT"}
                    </button>
                    <button className="btn-ghost" onClick={() => setRemoving(null)} data-testid="recipient-remove-no">ANNULER</button>
                  </div>
                )}
                {open === r.lead_id && r.message && (
                  <div className="mt-2 rounded-xl border border-border bg-black/20 p-3 text-xs space-y-1" data-testid="recipient-message">
                    <span className={`chip ${siteState(r.message.site_state).chip}`}>{siteState(r.message.site_state).label}</span>
                    <div className="font-medium">{r.message.subject}</div>
                    <pre className="whitespace-pre-wrap font-sans text-soft">{r.message.body}</pre>
                    <p className="text-faint">Le pied (identité, origine des données, désinscription) est ajouté par le serveur.</p>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
