import { useState } from "react";
import { toast } from "sonner";
import { Copy, EnvelopeSimple } from "@phosphor-icons/react";
import { emailProvidersApi, useAsync } from "@/lib/outreach";
import { activeApi, apiLine, providerVerdict, serverLines } from "@/lib/providerFormat";
import { ErrorBlock } from "@/components/outreach/States";

// The SMTP relays one can move to: public settings only, the login and password named, never filled in.
function SmtpRelays({ d }) {
  const [chosen, setChosen] = useState(null);
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
    <div className="space-y-2">
      <p className="text-sm text-soft">
        Un relais dédié remplace la messagerie mutualisée pour <strong>l&apos;envoi</strong> ; les réponses restent lues dans votre boîte actuelle
        ({d.replies_read ? "IMAP configuré" : "IMAP non configuré : les réponses ne sont pas lues"}). Les limites d&apos;envoi, le sandbox, la désinscription et
        toutes les portes restent en place. Un relais SMTP a besoin d&apos;un port sortant 587 ou 465, fermé sur une instance Render gratuite.
      </p>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Relais B2B">
        {d.relays.map((r) => (
          <button key={r.id} type="button" role="radio" aria-checked={relay && relay.id === r.id} onClick={() => setChosen(r.id)} data-testid={`relay-${r.id}`}
            className={`rounded-xl border px-3 py-1.5 text-sm transition-colors ${relay && relay.id === r.id ? "border-brand-violet bg-brand-violet/15 text-white" : "border-border text-soft hover:border-white/20"}`}>
            {r.name}{r.recommended ? " · recommandé en SMTP" : ""}{r.active ? " · actif" : ""}
          </button>
        ))}
      </div>
      {relay && (
        <div className="rounded-xl border border-border bg-card p-3 text-sm space-y-2" data-testid="relay-detail">
          <p className="text-soft">{relay.note} Identifiant : {relay.username_hint}.</p>
          <ol className="list-decimal space-y-1 pl-5 text-soft">
            <li>Créez le compte chez {relay.name}, vérifiez votre domaine (SPF, DKIM) et l&apos;adresse d&apos;expédition (OUTREACH_SENDER_EMAIL).</li>
            <li>Relisez ses conditions d&apos;utilisation : elles doivent autoriser la prospection B2B pour votre usage. L&apos;application ne le vérifie pas à votre place.</li>
            <li>Sur le serveur (Render › Environment), remplacez les variables SMTP par celles-ci, identifiant et mot de passe saisis là-bas, puis redéployez.</li>
          </ol>
          <pre className="overflow-x-auto rounded-lg border border-border bg-background/60 p-3 font-mono text-xs" data-testid="relay-lines">{lines.join("\n")}</pre>
          <button type="button" className="btn-ghost" onClick={copy} data-testid="relay-copy"><Copy size={14} /> COPIER LES RÉGLAGES</button>
        </div>
      )}
    </div>
  );
}

// « Fournisseur d'envoi » : the provider in use, then how to change it, in the order the server tries the channels (Resend,
// Brevo, then SMTP). A change is made on the server: a key or a password never goes through the application. Replies keep
// being read from the IMAP mailbox. With an API channel in use, the SMTP relays only matter if it is removed: they fold.
export default function ProviderSwitch() {
  const state = useAsync(() => emailProvidersApi.get(), [], { key: "email-providers", intervalMs: 60000 });
  const d = state.data;
  if (state.error && !d) return <ErrorBlock message={state.error} onRetry={state.reload} />;
  if (!d) return null;
  const verdict = providerVerdict(d.current);
  const api = activeApi(d);
  const channels = d.api_channels || [];
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

      {channels.length > 0 && (
        <div className="space-y-2" data-testid="api-channels">
          <h3 className="font-semibold">{api ? `${api.name} envoie l'e-mail` : "Le plus simple : une clé d'API"}</h3>
          <p className="text-sm text-soft" data-testid="api-order">
            {api
              ? `Le serveur essaie Resend, puis Brevo, puis SMTP : ${api.name} est le premier configuré, c'est lui qui envoie.`
              : "Le serveur essaie Resend, puis Brevo, puis SMTP. Une clé d'API passe par le port 443, ouvert là où les ports SMTP sortants sont fermés (une instance Render gratuite)."}
          </p>
          <ul className="space-y-2">
            {channels.map((c) => (
              <li key={c.id} className="rounded-xl border border-border bg-card p-3 text-sm" data-testid={`api-${c.id}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{c.name}{c.recommended ? " · recommandé" : ""}</span>
                  <span className={`chip ${c.active ? "chip-success" : c.configured ? "chip-warn" : "chip-ink"}`} data-testid={`api-${c.id}-state`}>
                    {c.active ? "utilisé" : c.configured ? "configuré, en réserve" : "non configuré"}
                  </span>
                </div>
                <p className="mt-1 text-soft">{c.note}</p>
                {!c.configured && <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-background/60 p-2 font-mono text-xs">{apiLine(c)}</pre>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {api ? (
        <details className="rounded-xl border border-border px-4 py-3" data-testid="smtp-relays">
          <summary className="cursor-pointer select-none text-sm font-semibold">Relais SMTP : inutilisés tant que {api.name} est configuré</summary>
          <div className="mt-3"><SmtpRelays d={d} /></div>
        </details>
      ) : (
        <div className="space-y-2" data-testid="smtp-relays">
          <h3 className="font-semibold">{channels.length > 0 ? "Ou un relais d'envoi B2B (SMTP)" : "Passer à un relais d'envoi B2B"}</h3>
          <SmtpRelays d={d} />
        </div>
      )}
      <p className="flex items-center gap-2 text-xs text-faint"><EnvelopeSimple size={14} aria-hidden="true" /> Variables du serveur : {d.server_variables.join(", ")} (noms seulement).</p>
    </section>
  );
}
