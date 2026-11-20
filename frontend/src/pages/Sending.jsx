import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise, CheckCircle, Pause, Play, Warning } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, outboundApi, prospectsApi, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import {
  LIMIT_RANGES, MESSAGE_STATUS_CHIP, MESSAGE_STATUS_LABEL, describeApiError, describeInboxSync, describeTestSend, describeWhatsappTest, formatDateTime, limitsPatch,
  validateLimits,
} from "@/lib/outreachFormat";
import { statusSummary } from "@/lib/sendingFormat";
import HistoryTimeline from "@/components/outreach/HistoryTimeline";
import PageShell from "@/components/PageShell";
import ProviderSwitch from "@/components/outreach/ProviderSwitch";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// The decision first (can a message leave now, and if not why), then the state as chips and the volumes on one line:
// everything from GET /outbound/status (lib/sendingFormat.js), nothing invented.
function StatusPanel({ status, settings }) {
  const summary = statusSummary(status, settings);
  return (
    <section className="space-y-3" data-testid="status-panel" aria-label="État de l'envoi">
      <p className={`flex items-start gap-2 text-lg font-semibold ${summary.canSend ? "text-foreground" : "text-brand-300"}`} role="status" data-testid="fact-can-send">
        {summary.canSend ? <CheckCircle size={20} weight="fill" className="mt-1 shrink-0 text-brand-400" /> : <Warning size={20} weight="fill" className="mt-1 shrink-0" />}
        {summary.headline}
      </p>
      <ul className="flex flex-wrap gap-2" aria-label="État">
        {summary.chips.map((c) => <li key={c.key} className={`chip ${c.tone}`} data-testid={c.testId}>{c.label}</li>)}
      </ul>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm" aria-label="Volumes">
        {summary.volumes.map((v) => (
          <div key={v.key}><dt className="inline text-faint">{v.label} : </dt><dd className="inline font-mono" data-testid={v.testId}>{v.value}</dd></div>
        ))}
      </dl>
      {settings && !settings.sender_configured && (
        <p className="flex gap-2 rounded-md border border-border bg-card p-3 text-sm text-soft" role="alert">
          <Warning size={16} className="mt-0.5 shrink-0" />
          Le serveur n&apos;a pas d&apos;identité d&apos;expéditeur (OUTREACH_SENDER_NAME, _COMPANY, _ADDRESS, _EMAIL) : aucun brouillon ne peut être préparé ni envoyé.
        </p>
      )}
      {settings && Object.keys(settings.usage).length > 0 && (
        <p className="text-sm text-soft" data-testid="usage">
          Usage enregistré : {Object.entries(settings.usage).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

function LimitsForm({ limits, canEdit, onSaved }) {
  const [values, setValues] = useState({
    max_per_day: String(limits.max_per_day), max_per_hour: String(limits.max_per_hour), min_delay_seconds: String(limits.min_delay_seconds),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const errors = validateLimits(values);
  const patch = limitsPatch(limits, values);
  const dirty = Object.keys(patch).length > 0;

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await outboundApi.putLimits(patch);
      toast.success("Limites enregistrées");
      await onSaved();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const togglePause = async () => {
    setBusy(true);
    setError(null);
    try {
      await outboundApi.putLimits({ sending_paused: !limits.sending_paused });
      toast.success(limits.sending_paused ? "Envoi repris" : "Envoi mis en pause");
      await onSaved();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-5 space-y-4" data-testid="limits-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-display text-xl font-bold">Limites</h2>
          <p className="text-sm text-soft">Appliquées avant chaque envoi. Le jour est le jour calendaire dans le fuseau horaire du compte.</p>
        </div>
        <button className={limits.sending_paused ? "btn-primary" : "btn-ghost"} onClick={togglePause} disabled={!canEdit || busy} data-testid="toggle-pause"
          title="Arrête tous les envois de ce compte jusqu'à la reprise">
          {limits.sending_paused ? <><Play size={14} weight="fill" /> REPRENDRE L&apos;ENVOI</> : <><Pause size={14} weight="fill" /> METTRE L&apos;ENVOI EN PAUSE</>}
        </button>
      </div>
      <form onSubmit={save} className="space-y-3">
        <div className="grid md:grid-cols-3 gap-4">
          {Object.entries(LIMIT_RANGES).map(([key, r]) => (
            <label key={key} className="block text-sm">
              <span className="mono-accent block mb-1">{r.label}</span>
              <input type="number" inputMode="numeric" min={r.min} max={r.max} step={1} className="neo-input" value={values[key]} disabled={!canEdit}
                onChange={(e) => setValues({ ...values, [key]: e.target.value })} data-testid={`limit-${key}`} aria-invalid={!!errors[key]} />
              {errors[key] && <span className="text-xs text-red-300" data-testid={`limit-error-${key}`}>{errors[key]}</span>}
            </label>
          ))}
        </div>
        {error && <div role="alert" className="text-sm text-red-300 bg-red-500/10 border border-red-400/40 rounded-md p-3" data-testid="limits-error">{error}</div>}
        <div className="flex items-center gap-3">
          <button className="btn-ink" type="submit" disabled={!canEdit || busy || !dirty || Object.keys(errors).length > 0} data-testid="save-limits">ENREGISTRER LES LIMITES</button>
          {!canEdit && <span className="mono-accent text-faint">réservé au propriétaire ou à un administrateur</span>}
        </div>
      </form>
    </section>
  );
}

function MessageRow({ message, canEdit, onChanged }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const detail = useAsync(() => (open ? outboundApi.get(message.id) : Promise.resolve(null)), [open, message.id, message.status]);

  const simulate = async (event) => {
    setBusy(true);
    setError(null);
    try {
      await outboundApi.simulate(message.id, event, text);
      toast.success(event === "bounced" ? "Rebond simulé : adresse supprimée" : "Réponse simulée");
      setText("");
      await onChanged();
      detail.reload();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const events = detail.data
    ? detail.data.events.map((e) => ({ key: e.id, at: e.created_at, label: e.event_type, actor: "fournisseur (simulé)", detail: e.detail }))
    : [];

  return (
    <Fragment>
      <tr className="border-b border-border hover:bg-white/[0.04] cursor-pointer" onClick={() => setOpen(!open)} data-testid="message-row">
        <td className="p-3 font-mono text-xs">{formatDateTime(message.dispatched_at)}</td>
        <td className="p-3">{message.to_email || <span className="text-faint">effacée</span>}</td>
        <td className="p-3 hidden md:table-cell truncate max-w-xs">{message.subject}</td>
        <td className="p-3"><span className={`chip ${MESSAGE_STATUS_CHIP[message.status] || "chip"}`}>{MESSAGE_STATUS_LABEL[message.status] || message.status}</span></td>
        <td className="p-3">{message.dry_run ? <span className="chip chip-ink">simulation</span> : <span className="chip chip-warn">réel</span>}</td>
      </tr>
      {open && (
        <tr className="bg-white/[0.04] border-b border-border" data-testid="message-detail">
          <td colSpan={5} className="p-4 space-y-3">
            <div className="flex flex-wrap gap-3 text-sm">
              <Link to={`/app/prospects/${message.lead_id}`} className="underline">ouvrir le prospect</Link>
              <span className="mono-accent text-soft">canal {message.adapter} · id {message.provider_message_id || "—"}</span>
            </div>
            {detail.loading && <LoadingBlock label="Chargement des événements…" />}
            {detail.error && <ErrorBlock message={detail.error} onRetry={detail.reload} />}
            {detail.data && <HistoryTimeline items={events} />}
            {message.dry_run && canEdit && message.status !== "bounced" && message.status !== "failed" && (
              <div className="border-t border-border pt-3 space-y-2" data-testid="simulate-box">
                <p className="mono-accent">simulation · remplace le retour du fournisseur, mêmes effets</p>
                {error && <div role="alert" className="text-sm text-red-300" data-testid="simulate-error">{error}</div>}
                <div className="flex flex-wrap gap-2 items-center">
                  <input className="neo-input !w-72" placeholder="Texte de la réponse (essayez : STOP)" value={text} onChange={(e) => setText(e.target.value)} data-testid="simulate-text" />
                  <button className="btn-ghost" disabled={busy || !text.trim()} onClick={() => simulate("replied")} data-testid="simulate-reply">SIMULER UNE RÉPONSE</button>
                  <button className="btn-ghost" disabled={busy} onClick={() => simulate("bounced")} data-testid="simulate-bounce">SIMULER UN REBOND DÉFINITIF</button>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </Fragment>
  );
}

const TONE_TEXT = { ok: "text-emerald-300", warn: "text-amber-300", danger: "text-red-300" };

function InboxSyncPanel({ onDone }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const sync = async () => {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(describeInboxSync(await outboundApi.syncInbox()));
      onDone();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-5 space-y-3" data-testid="inbox-sync">
      <h2 className="font-display text-xl font-bold">Réponses et rebonds</h2>
      <p className="text-sm text-soft">
        Lit la boîte d&apos;envoi en IMAP (IMAP_HOST, IMAP_USERNAME et IMAP_PASSWORD). Une réponse est enregistrée avec un court extrait,
        un STOP du destinataire le désinscrit, et seul un échec de remise définitif supprime une adresse. Là où un worker tourne, cela se
        fait aussi toutes les 5 minutes. Sous Resend, les rebonds arrivent par son webhook signé, pas par cette boîte.
      </p>
      <button className="btn-ghost" disabled={busy} onClick={sync} data-testid="inbox-sync-run">{busy ? "LECTURE…" : "LIRE LA BOÎTE MAINTENANT"}</button>
      {result && <div role="status" className="text-sm text-emerald-300" data-testid="inbox-sync-result">{result}</div>}
      {error && <div role="alert" className="text-sm text-red-300" data-testid="inbox-sync-error">{error}</div>}
    </section>
  );
}

function SmtpTestPanel({ onDone }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const send = async () => {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(describeTestSend(await outboundApi.testSend(to.trim())));
      onDone();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-5 space-y-3" data-testid="smtp-test">
      <h2 className="font-display text-xl font-bold">Tester le canal e-mail réel</h2>
      <p className="text-sm text-soft">
        Envoie un message technique (pas de prospection) à l&apos;adresse de l&apos;expéditeur ou à la liste autorisée du bac à sable, par le
        canal réel (Resend, puis Brevo, puis SMTP, selon la configuration), avec les mêmes limites et le même arrêt d&apos;urgence. Il faut
        l&apos;envoi réel activé et un canal configuré ; sinon c&apos;est refusé et rien ne part.
      </p>
      <div className="flex gap-2 flex-wrap items-center">
        <input className="neo-input !w-72" type="email" placeholder="founder@plantiers.com" value={to}
          onChange={(e) => setTo(e.target.value)} data-testid="smtp-test-to" />
        <button className="btn-ghost" disabled={busy || !to.trim()} onClick={send} data-testid="smtp-test-send">
          {busy ? "ENVOI…" : "ENVOYER L’E-MAIL DE TEST"}
        </button>
      </div>
      {result && <div role="status" className={`text-sm ${TONE_TEXT[result.tone]}`} data-testid="smtp-test-result">{result.text}</div>}
      {error && <div role="alert" className="text-sm text-red-300" data-testid="smtp-test-error">{error}</div>}
    </section>
  );
}

function WhatsappTestPanel({ onDone }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const send = async () => {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(describeWhatsappTest(await outboundApi.testWhatsapp(to.trim())));
      onDone();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-5 space-y-3" data-testid="whatsapp-test">
      <h2 className="font-display text-xl font-bold">Tester le canal WhatsApp réel</h2>
      <p className="text-sm text-soft">
        Envoie un message technique (pas de prospection) à un numéro listé dans <code>OUTREACH_LIVE_PHONES</code> (votre propre téléphone), avec
        les mêmes limites et le même arrêt d&apos;urgence. Il faut les réglages Twilio ; sinon c&apos;est refusé et rien ne part.
      </p>
      <div className="flex gap-2 flex-wrap items-center">
        <input className="neo-input !w-72" type="tel" placeholder="+33612345678" value={to}
          onChange={(e) => setTo(e.target.value)} data-testid="whatsapp-test-to" />
        <button className="btn-ghost" disabled={busy || !to.trim()} onClick={send} data-testid="whatsapp-test-send">
          {busy ? "ENVOI…" : "ENVOYER LE WHATSAPP DE TEST"}
        </button>
      </div>
      {result && <div role="status" className={`text-sm ${TONE_TEXT[result.tone]}`} data-testid="whatsapp-test-result">{result.text}</div>}
      {error && <div role="alert" className="text-sm text-red-300" data-testid="whatsapp-test-error">{error}</div>}
    </section>
  );
}

export default function Sending() {
  const { user } = useAuth();
  const edit = canDecide(user);
  const page = useAsync(async () => {
    const [status, limits, messages, settings] = await Promise.all([
      outboundApi.status(), outboundApi.limits(), outboundApi.list({ limit: 100 }), prospectsApi.settings().catch(() => null),
    ]);
    return { status, limits, messages, settings };
  }, [], { key: "sending", intervalMs: LIVE_MS });

  const tools = page.data && edit ? (
    <>
      <SmtpTestPanel onDone={page.reload} />
      <WhatsappTestPanel onDone={page.reload} />
      <InboxSyncPanel onDone={page.reload} />
    </>
  ) : null;

  return (
    <PageShell
      testId="sending-page"
      kicker="outreach · canaux"
      title="Canaux d'envoi"
      lead="Ce qui permet à un message de partir maintenant, les limites, l'arrêt d'urgence et l'historique. Simulation par défaut ; en envoi réel, l'e-mail part par Resend, puis Brevo, puis SMTP, selon ce qui est configuré. Un message resté « sending » a une issue inconnue : vérifiez la boîte d'envoi avant de renvoyer."
      action={<button className="btn-ghost" onClick={page.reload} data-testid="refresh"><ArrowsClockwise size={14} /> ACTUALISER</button>}
      details={tools}
      detailsLabel="Tests et outils (e-mail, WhatsApp, boîte de réception)"
    >
      {page.loading && !page.data && <LoadingBlock label="Chargement de l'état d'envoi…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}

      {page.data && (
        <>
          <StatusPanel status={page.data.status} settings={page.data.settings} />
          <ProviderSwitch />
          <LimitsForm key={JSON.stringify(page.data.limits)} limits={page.data.limits} canEdit={edit} onSaved={page.reload} />
          <section className="space-y-3" data-testid="messages-panel">
            <h2 className="font-display text-xl font-bold">Messages envoyés</h2>
            {page.data.messages.length === 0 ? (
              <EmptyBlock title="Aucun message envoyé" testId="messages-empty">
                <p>Approuvez un prospect, préparez et approuvez un brouillon, puis envoyez-le depuis la fiche du prospect. Il apparaîtra ici.</p>
                <Link to="/app/prospects" className="btn-ink inline-flex">VOIR LES PROSPECTS</Link>
              </EmptyBlock>
            ) : (
              <div className="surface overflow-hidden">
                <table className="w-full text-sm" data-testid="messages-table">
                  <thead className="bg-white/[0.04] border-b border-border">
                    <tr className="text-left mono-accent">
                      <th className="p-3">quand</th><th className="p-3">à</th><th className="p-3 hidden md:table-cell">objet</th><th className="p-3">statut</th><th className="p-3">mode</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.data.messages.map((m) => <MessageRow key={m.id} message={m} canEdit={edit} onChanged={page.reload} />)}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </PageShell>
  );
}
