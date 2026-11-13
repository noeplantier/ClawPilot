import { useState } from "react";
import { toast } from "sonner";
import { Lightning, Sparkle } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { autoSelectionApi, canDecide, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import { describeApiError } from "@/lib/outreachFormat";

// The server's own selection: among the prospects waiting for review, those its eligibility policy qualifies (e-mail, phone,
// address, position on a fresh source, a fit score), hottest first. The person approves the whole selection in one click;
// each decision is audited, the suppression list is checked for each, and nothing is sent.
export default function AutoSelection({ onDecided }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const sel = useAsync(() => autoSelectionApi.selection(200), [], { key: "auto:selection", intervalMs: LIVE_MS });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const d = sel.data;
  if (!d || d.total === 0) return null; // nothing qualified waits: the queue below says the rest
  const approveAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await autoSelectionApi.review(d.items.map((i) => i.id), "approve");
      const extra = [out.suppressed ? `${out.suppressed} sur la liste d'opposition` : "", out.skipped ? `${out.skipped} déjà décidé(s)` : ""].filter(Boolean).join(", ");
      toast.success(`${out.approved} prospect(s) approuvé(s) et ajouté(s) au CRM${extra ? ` (${extra})` : ""}. Rien n'a été envoyé.`);
      sel.reload();
      if (onDecided) onDecided();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="rounded-2xl border border-brand-violet/40 bg-brand-violet/10 p-4 space-y-3" aria-label="Sélection automatique" data-testid="auto-selection">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Sparkle size={22} weight="duotone" className="mt-0.5 shrink-0 text-brand-lilac" aria-hidden="true" />
          <div>
            <h2 className="font-display text-lg font-bold" data-testid="auto-selection-title">
              {d.total} prospect{d.total === 1 ? "" : "s"} qualifié{d.total === 1 ? "" : "s"} sélectionné{d.total === 1 ? "" : "s"} pour vous
            </h2>
            <p className="text-sm text-soft">
              E-mail, téléphone, adresse et position connus, score récent{d.hot ? ` · dont ${d.hot} avec une intention commerciale observée` : ""}. Le plus chaud d&apos;abord.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="auto-selection-toggle">
            {open ? "MASQUER LA LISTE" : "VOIR LA LISTE"}
          </button>
          {decide && (
            <button type="button" className="btn-primary" disabled={busy} onClick={approveAll} data-testid="auto-selection-approve">
              <Lightning size={14} weight="bold" /> {busy ? "APPROBATION…" : `APPROUVER LES ${d.total}`}
            </button>
          )}
        </div>
      </div>
      {open && (
        <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-xl border border-border bg-card text-sm" data-testid="auto-selection-list">
          {d.items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="min-w-0 truncate"><span className="font-medium">{i.name}</span>{i.city ? <span className="text-soft"> · {i.city}</span> : null}</span>
              <span className="shrink-0 font-mono text-[11px] text-soft">{i.priority === "hot" ? "HOT" : "qualifié"} · {typeof i.score === "number" ? `score ${i.score}` : "non scoré"}</span>
            </li>
          ))}
        </ul>
      )}
      {!decide && <p className="text-xs text-soft">Seul un propriétaire ou un administrateur approuve la sélection.</p>}
      {error && <p role="alert" className="text-sm text-red-300" data-testid="auto-selection-error">{error}</p>}
    </section>
  );
}
