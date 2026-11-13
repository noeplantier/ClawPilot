import { useState } from "react";
import { toast } from "sonner";
import { Lock, LockOpen } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import PageShell from "@/components/PageShell";
import MandateForm from "@/components/mandate/MandateForm";
import MandateCard from "@/components/mandate/MandateCard";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import { canDecide, journeysApi, mandatesApi, useAsync } from "@/lib/outreach";
import { launchError } from "@/lib/launchFormat";

// « Automatisation max » : un mandat explicite, borné (zone, message, expéditeur, plafonds, durée, arrêts), désactivé par défaut sur le
// serveur. Un mandat n'élargit jamais rien : pas de nouvelle zone, pas de nouveau message, pas de découverte automatique.
export default function AutomationMax({ embedded = false }) {
  const { user } = useAuth();
  const decide = canDecide(user);
  const owner = user && user.role === "owner";
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reports, setReports] = useState({});
  const overview = useAsync(() => mandatesApi.overview(), [version], { key: "mandates:overview", intervalMs: 30000 });
  const journeys = useAsync(() => journeysApi.list(), [version], { key: "journeys:list", intervalMs: 60000 });

  const act = async (name, fn, done) => {
    setBusy(name);
    setError("");
    try {
      const out = await fn();
      if (done) toast.success(done);
      return out;
    } catch (e) {
      setError(launchError(e));
      return null;
    } finally {
      setBusy("");
      setVersion((n) => n + 1);
    }
  };
  const report = async (id) => {
    const out = await act("report", () => mandatesApi.report(id));
    if (out) setReports((r) => ({ ...r, [id]: out }));
  };
  const after = (name, id, fn, done) => act(name, async () => { const out = await fn(); if (reports[id]) setReports((r) => ({ ...r, [id]: undefined })); return out; }, done);

  const o = overview.data;
  return (
    <PageShell
      embedded={embedded}
      testId="max-page"
      kicker="outreach.automatisation-max"
      title="Automatisation max"
      lead="Une seule autorisation, explicite et bornée : le système envoie dans ces limites, s'arrête de lui-même, et vous pouvez tout révoquer à tout instant."
    >
      {overview.error && !o && <ErrorBlock message={overview.error} onRetry={overview.reload} />}
      {!o && !overview.error && <LoadingBlock label="Chargement…" />}
      {o && (
        <>
          <div className={`flex items-start gap-3 rounded-2xl border p-4 ${o.enabled ? "border-brand-violet/50 bg-brand-violet/10" : "border-border bg-card"}`} data-testid="max-switch" role="status">
            {o.enabled ? <LockOpen size={22} className="mt-0.5 shrink-0 text-brand-lilac" aria-hidden="true" /> : <Lock size={22} className="mt-0.5 shrink-0 text-faint" aria-hidden="true" />}
            <div className="text-sm">
              <div className="font-semibold" data-testid="max-switch-state">{o.enabled ? "Disponible sur ce serveur" : "Désactivé sur ce serveur"}</div>
              <p className="text-soft">{o.enabled ? "Rien n'agit tant qu'un mandat n'a pas été autorisé explicitement par un propriétaire." : `${o.why_disabled}. L'activer est une décision de l'opérateur du serveur ; cet écran ne peut pas le faire.`}</p>
              {!o.reply_collection_configured && <p className="text-amber-300">Les réponses ne sont pas lues (IMAP non configuré) : le serveur refusera d&apos;activer un mandat.</p>}
            </div>
          </div>
          {error && <p role="alert" className="rounded-xl border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-300" data-testid="max-error">{error}</p>}

          <section aria-label="Mandats" className="space-y-4">
            <h2 className="font-display text-xl font-bold">Mandats</h2>
            {o.mandates.length === 0 && <EmptyBlock title="Aucun mandat" testId="max-empty">Rien n&apos;est automatisé. Un mandat se crée en brouillon : il n&apos;agit qu&apos;une fois autorisé.</EmptyBlock>}
            {o.mandates.map((m) => (
              <MandateCard
                key={m.id} mandate={m} overview={o} report={reports[m.id]} decide={decide} owner={owner} busy={busy}
                onActivate={(id, acks) => after("activate", id, () => mandatesApi.activate(id, acks), "Mandat activé : il agit désormais dans ses limites.")}
                onSuspend={(id) => after("suspend", id, () => mandatesApi.suspend(id), "Mandat en pause : rien ne part.")}
                onRevoke={(id) => after("revoke", id, () => mandatesApi.revoke(id), "Mandat révoqué : les envois planifiés sont annulés.")}
                onRevalidate={(id) => after("revalidate", id, () => mandatesApi.revalidate(id), "Mandat revalidé : autorisez-le à nouveau pour reprendre.")}
                onReport={report}
              />
            ))}
          </section>

          {decide && o.enabled && journeys.data && (
            <section aria-label="Nouveau mandat" className="rounded-2xl border border-border bg-card p-4 space-y-3">
              <h2 className="font-display text-xl font-bold">Nouveau mandat</h2>
              <MandateForm limits={o.limits} journeys={journeys.data} busy={busy} onCreate={(payload) => act("create", () => mandatesApi.create(payload), "Mandat créé en brouillon : il n'agit pas encore.")} />
            </section>
          )}
        </>
      )}
    </PageShell>
  );
}
