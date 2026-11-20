import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise, CheckCircle, Pause, Play, Warning } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, outboundApi, prospectsApi, useAsync } from "@/lib/outreach";
import { LIVE_MS } from "@/lib/live";
import {
  LIMIT_RANGES, MESSAGE_STATUS_CHIP, describeApiError, describeInboxSync, describeTestSend, describeWhatsappTest, formatDateTime, limitsPatch,
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
      toast.success("Limits saved");
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
      toast.success(limits.sending_paused ? "Sending resumed" : "Sending paused");
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
          <h2 className="font-display text-xl font-bold">Limits</h2>
          <p className="text-sm text-soft">Applied before every dispatch. The day is the calendar day in the organisation’s timezone.</p>
        </div>
        <button className={limits.sending_paused ? "btn-primary" : "btn-ghost"} onClick={togglePause} disabled={!canEdit || busy} data-testid="toggle-pause"
          title="Stops all dispatches for this organisation until resumed">
          {limits.sending_paused ? <><Play size={14} weight="fill" /> RESUME SENDING</> : <><Pause size={14} weight="fill" /> PAUSE SENDING</>}
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
          <button className="btn-ink" type="submit" disabled={!canEdit || busy || !dirty || Object.keys(errors).length > 0} data-testid="save-limits">SAVE LIMITS</button>
          {!canEdit && <span className="mono-accent text-faint">requires owner or admin</span>}
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
      toast.success(event === "bounced" ? "Bounce simulated: address suppressed" : "Reply simulated");
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
    ? detail.data.events.map((e) => ({ key: e.id, at: e.created_at, label: e.event_type, actor: "provider (simulated)", detail: e.detail }))
    : [];

  return (
    <Fragment>
      <tr className="border-b border-border hover:bg-white/[0.04] cursor-pointer" onClick={() => setOpen(!open)} data-testid="message-row">
        <td className="p-3 font-mono text-xs">{formatDateTime(message.dispatched_at)}</td>
        <td className="p-3">{message.to_email || <span className="text-faint">erased</span>}</td>
        <td className="p-3 hidden md:table-cell truncate max-w-xs">{message.subject}</td>
        <td className="p-3"><span className={`chip ${MESSAGE_STATUS_CHIP[message.status] || "chip"}`}>{message.status}</span></td>
        <td className="p-3">{message.dry_run ? <span className="chip chip-ink">dry-run</span> : <span className="chip chip-warn">live</span>}</td>
      </tr>
      {open && (
        <tr className="bg-white/[0.04] border-b border-border" data-testid="message-detail">
          <td colSpan={5} className="p-4 space-y-3">
            <div className="flex flex-wrap gap-3 text-sm">
              <Link to={`/app/prospects/${message.lead_id}`} className="underline">open the prospect</Link>
              <span className="mono-accent text-soft">adapter {message.adapter} · id {message.provider_message_id || "—"}</span>
            </div>
            {detail.loading && <LoadingBlock label="Loading events…" />}
            {detail.error && <ErrorBlock message={detail.error} onRetry={detail.reload} />}
            {detail.data && <HistoryTimeline items={events} />}
            {message.dry_run && canEdit && message.status !== "bounced" && message.status !== "failed" && (
              <div className="border-t border-border pt-3 space-y-2" data-testid="simulate-box">
                <p className="mono-accent">simulation · stands in for the provider webhook, same effects</p>
                {error && <div role="alert" className="text-sm text-red-300" data-testid="simulate-error">{error}</div>}
                <div className="flex flex-wrap gap-2 items-center">
                  <input className="neo-input !w-72" placeholder="Reply text (try: STOP)" value={text} onChange={(e) => setText(e.target.value)} data-testid="simulate-text" />
                  <button className="btn-ghost" disabled={busy || !text.trim()} onClick={() => simulate("replied")} data-testid="simulate-reply">SIMULATE REPLY</button>
                  <button className="btn-ghost" disabled={busy} onClick={() => simulate("bounced")} data-testid="simulate-bounce">SIMULATE HARD BOUNCE</button>
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
      <h2 className="font-display text-xl font-bold">Replies and bounces</h2>
      <p className="text-sm text-soft">
        Reads the sending mailbox over IMAP (needs IMAP_HOST, IMAP_USERNAME and IMAP_PASSWORD). A reply is recorded with a short
        excerpt, a STOP from the recipient opts them out, and only a permanent delivery failure suppresses an address.
        Where a worker runs, this also happens every 5 minutes.
      </p>
      <button className="btn-ghost" disabled={busy} onClick={sync} data-testid="inbox-sync-run">{busy ? "READING…" : "READ MAILBOX NOW"}</button>
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
      <h2 className="font-display text-xl font-bold">Test the real e-mail connection</h2>
      <p className="text-sm text-soft">
        Sends one technical message (not prospecting) to the sender&apos;s own address or to the sandbox allowlist, through the
        same limits and kill switch. Needs live sending and the SMTP settings; otherwise it is refused and nothing is sent.
      </p>
      <div className="flex gap-2 flex-wrap items-center">
        <input className="neo-input !w-72" type="email" placeholder="founder@plantiers.com" value={to}
          onChange={(e) => setTo(e.target.value)} data-testid="smtp-test-to" />
        <button className="btn-ghost" disabled={busy || !to.trim()} onClick={send} data-testid="smtp-test-send">
          {busy ? "SENDING…" : "SEND TEST E-MAIL"}
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
      <h2 className="font-display text-xl font-bold">Test the real WhatsApp connection</h2>
      <p className="text-sm text-soft">
        Sends one technical message (not prospecting) to a number listed in <code>OUTREACH_LIVE_PHONES</code> (your own phone), through the same
        limits and kill switch. Needs the Twilio settings; otherwise it is refused and nothing is sent.
      </p>
      <div className="flex gap-2 flex-wrap items-center">
        <input className="neo-input !w-72" type="tel" placeholder="+33612345678" value={to}
          onChange={(e) => setTo(e.target.value)} data-testid="whatsapp-test-to" />
        <button className="btn-ghost" disabled={busy || !to.trim()} onClick={send} data-testid="whatsapp-test-send">
          {busy ? "SENDING…" : "SEND TEST WHATSAPP"}
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
      {page.loading && !page.data && <LoadingBlock label="Loading sending status…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}

      {page.data && (
        <>
          <StatusPanel status={page.data.status} settings={page.data.settings} />
          <ProviderSwitch />
          <LimitsForm key={JSON.stringify(page.data.limits)} limits={page.data.limits} canEdit={edit} onSaved={page.reload} />
          <section className="space-y-3" data-testid="messages-panel">
            <h2 className="font-display text-xl font-bold">Dispatched messages</h2>
            {page.data.messages.length === 0 ? (
              <EmptyBlock title="No message has been dispatched" testId="messages-empty">
                <p>Approve a prospect, prepare and approve a draft, then dispatch it from the prospect page. It will appear here.</p>
                <Link to="/app/prospects" className="btn-ink inline-flex">GO TO PROSPECTS</Link>
              </EmptyBlock>
            ) : (
              <div className="surface overflow-hidden">
                <table className="w-full text-sm" data-testid="messages-table">
                  <thead className="bg-white/[0.04] border-b border-border">
                    <tr className="text-left mono-accent">
                      <th className="p-3">when</th><th className="p-3">to</th><th className="p-3 hidden md:table-cell">subject</th><th className="p-3">status</th><th className="p-3">mode</th>
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
