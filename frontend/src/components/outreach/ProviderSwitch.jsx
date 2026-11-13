import { useState } from "react";
import { toast } from "sonner";
import { Copy, EnvelopeSimple } from "@phosphor-icons/react";
import { emailProvidersApi, useAsync } from "@/lib/outreach";
import { providerVerdict, serverLines } from "@/lib/providerFormat";
import { ErrorBlock } from "@/components/outreach/States";

// « Fournisseur d'envoi » : the provider in use, and the dedicated B2B relays one can move to. The move is made on the server
// (SMTP_*): a password never goes through the application. Replies keep being read from the IMAP mailbox.
export default function ProviderSwitch() {
  const state = useAsync(() => emailProvidersApi.get(), [], { key: "email-providers", intervalMs: 60000 });
  const d = state.data;
  const [chosen, setChosen] = useState(null);
  if (state.error && !d) return <ErrorBlock message={state.error} onRetry={state.reload} />;
  if (!d) return null;
  const verdict = providerVerdict(d.current);
  const relay = d.relays.find((r) => r.id === (chosen || (d.relays.find((x) => x.recommended) || d.relays[0]).id));
  const lines = serverLines(relay);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast.success("Réglages copiés : collez-les dans les variables d'environnement du serveur.");
    } catch {
      toast.error("Copie impossible : sélectionnez le texte à la main.");
    }
  };
  return (
    <section className="surface p-5 space-y-4" aria-label="Fournisseur d'envoi" data-testid="provider-switch">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Fournisseur d&apos;envoi</div>
          <h2 className="mt-2 font-display text-lg font-bold" data-testid="provider-current">{d.current.label}</h2>
          <p className="mt-1 max-w-2xl text-sm text-soft">{d.current.restriction}</p>
        </div>
        <span className={`chip chip-${verdict.tone}`} data-testid="provider-verdict">{verdict.label}</span>
      </header>

      <div className="space-y-2">
        <h3 className="font-semibold">Passer à un relais d&apos;envoi B2B</h3>
        <p className="text-sm text-soft">
          Un relais dédié remplace la messagerie mutualisée pour <strong>l&apos;envoi</strong> ; les réponses restent lues dans votre boîte actuelle
          ({d.replies_read ? "IMAP configuré" : "IMAP non configuré : les réponses ne sont pas lues"}). Les limites d&apos;envoi, le sandbox, la désinscription et
          toutes les portes restent en place.
        </p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Relais B2B">
          {d.relays.map((r) => (
            <button key={r.id} type="button" role="radio" aria-checked={relay && relay.id === r.id} onClick={() => setChosen(r.id)} data-testid={`relay-${r.id}`}
              className={`rounded-xl border px-3 py-1.5 text-sm transition-colors ${relay && relay.id === r.id ? "border-brand-violet bg-brand-violet/15 text-white" : "border-border text-soft hover:border-white/20"}`}>
              {r.name}{r.recommended ? " · recommandé" : ""}{r.active ? " · actif" : ""}
            </button>
          ))}
        </div>
        {relay && (
          <div className="rounded-xl border border-border bg-card p-3 text-sm space-y-2" data-testid="relay-detail">
            <p className="text-soft">{relay.note} Identifiant : {relay.username_hint}.</p>
            <ol className="list-decimal space-y-1 pl-5 text-soft">
              <li>Créez le compte chez {relay.name}, vérifiez votre domaine (SPF, DKIM) et l&apos;adresse d&apos;expédition ({d.current.host ? "celle de OUTREACH_SENDER_EMAIL" : "OUTREACH_SENDER_EMAIL"}).</li>
              <li>Relisez ses conditions d&apos;utilisation : elles doivent autoriser la prospection B2B pour votre usage. L&apos;application ne le vérifie pas à votre place.</li>
              <li>Sur le serveur (Render › Environment), remplacez les variables SMTP par celles-ci, identifiant et mot de passe saisis là-bas, puis redéployez.</li>
            </ol>
            <pre className="overflow-x-auto rounded-lg border border-border bg-background/60 p-3 font-mono text-xs" data-testid="relay-lines">{lines.join("\n")}</pre>
            <button type="button" className="btn-ghost" onClick={copy} data-testid="relay-copy"><Copy size={14} /> COPIER LES RÉGLAGES</button>
          </div>
        )}
      </div>
      <p className="flex items-center gap-2 text-xs text-faint"><EnvelopeSimple size={14} aria-hidden="true" /> Variables du serveur : {d.server_variables.join(", ")} (noms seulement).</p>
    </section>
  );
}
