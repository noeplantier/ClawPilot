import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowsClockwise, Pause, Play, Warning } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, outboundApi, prospectsApi, useAsync } from "@/lib/outreach";
import {
  LIMIT_RANGES, MESSAGE_STATUS_CHIP, describeApiError, describeTestSend, formatDateTime, formatRetry, limitsPatch,
  validateLimits,
} from "@/lib/outreachFormat";
import HistoryTimeline from "@/components/outreach/HistoryTimeline";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const BLOCKED_TEXT = {
  kill_switch: "kill switch (environment)",
  paused: "paused for this organisation",
  daily: "daily limit reached",
  hourly: "hourly limit reached",
  delay: "minimum delay not elapsed",
};

function Fact({ label, children, testId }) {
  return (
    <div className="border border-[#D6D3C8] rounded-md p-3 bg-white">
      <div className="mono-accent">{label}</div>
      <div className="font-display font-semibold mt-1" data-testid={testId}>{children}</div>
    </div>
  );
}

function StatusPanel({ status, settings }) {
  const blocked = status.blocked_by;
  const next = formatRetry(status.next_allowed_at);
  return (
    <section className="surface p-5 space-y-4" data-testid="status-panel">
      <h2 className="font-display text-xl font-bold">Status</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Fact label="mode" testId="fact-mode">{status.dry_run ? "Dry-run (nothing is delivered)" : "Live"}</Fact>
        <Fact label="kill switch" testId="fact-kill">{status.kill_switch ? "ON: all sending halted" : "off"}</Fact>
        <Fact label="this organisation" testId="fact-paused">{status.paused ? "paused" : "active"}</Fact>
        <Fact label="can send now" testId="fact-can-send">
          {blocked ? `no: ${BLOCKED_TEXT[blocked] || blocked}${next ? ` · try again ${next}` : ""}` : "yes"}
        </Fact>
        <Fact label="dispatched today" testId="fact-today">{status.sent_today}</Fact>
        <Fact label="last hour" testId="fact-hour">{status.sent_last_hour}</Fact>
        <Fact label="last dispatch">{status.last_dispatched_at ? formatDateTime(status.last_dispatched_at) : "none yet"}</Fact>
        <Fact label="sender identity" testId="fact-sender">{settings && settings.sender_configured ? "configured" : "not configured"}</Fact>
      </div>
      {settings && !settings.sender_configured && (
        <p className="text-sm text-[#92400E] bg-[#FFFBEB] border border-[#F59E0B]/40 rounded-md p-3 flex gap-2" role="alert">
          <Warning size={16} className="shrink-0 mt-0.5" />
          The server has no sender identity (OUTREACH_SENDER_NAME, _COMPANY, _ADDRESS, _EMAIL), so no draft can be prepared or dispatched.
        </p>
      )}
      {settings && Object.keys(settings.usage).length > 0 && (
        <p className="text-sm text-[#475569]" data-testid="usage">
          Recorded usage: {Object.entries(settings.usage).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}
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
          <p className="text-sm text-[#5F5F5A]">Applied before every dispatch. The day is the calendar day in the organisation’s timezone.</p>
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
              {errors[key] && <span className="text-xs text-[#991B1B]" data-testid={`limit-error-${key}`}>{errors[key]}</span>}
            </label>
          ))}
        </div>
        {error && <div role="alert" className="text-sm text-[#991B1B] bg-[#FEF2F2] border border-[#FCA5A5] rounded-md p-3" data-testid="limits-error">{error}</div>}
        <div className="flex items-center gap-3">
          <button className="btn-ink" type="submit" disabled={!canEdit || busy || !dirty || Object.keys(errors).length > 0} data-testid="save-limits">SAVE LIMITS</button>
          {!canEdit && <span className="mono-accent text-[#999995]">requires owner or admin</span>}
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
      <tr className="border-b border-[#EDEBE0] hover:bg-[#FAF9F3] cursor-pointer" onClick={() => setOpen(!open)} data-testid="message-row">
        <td className="p-3 font-mono text-xs">{formatDateTime(message.dispatched_at)}</td>
        <td className="p-3">{message.to_email || <span className="text-[#999995]">erased</span>}</td>
        <td className="p-3 hidden md:table-cell truncate max-w-xs">{message.subject}</td>
        <td className="p-3"><span className={`chip ${MESSAGE_STATUS_CHIP[message.status] || "chip"}`}>{message.status}</span></td>
        <td className="p-3">{message.dry_run ? <span className="chip chip-ink">dry-run</span> : <span className="chip chip-warn">live</span>}</td>
      </tr>
      {open && (
        <tr className="bg-[#FAFAF7] border-b border-[#D6D3C8]" data-testid="message-detail">
          <td colSpan={5} className="p-4 space-y-3">
            <div className="flex flex-wrap gap-3 text-sm">
              <Link to={`/app/prospects/${message.lead_id}`} className="underline">open the prospect</Link>
              <span className="mono-accent text-[#5F5F5A]">adapter {message.adapter} · id {message.provider_message_id || "—"}</span>
            </div>
            {detail.loading && <LoadingBlock label="Loading events…" />}
            {detail.error && <ErrorBlock message={detail.error} onRetry={detail.reload} />}
            {detail.data && <HistoryTimeline items={events} />}
            {message.dry_run && canEdit && message.status !== "bounced" && message.status !== "failed" && (
              <div className="border-t border-[#D6D3C8] pt-3 space-y-2" data-testid="simulate-box">
                <p className="mono-accent">simulation · stands in for the provider webhook, same effects</p>
                {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="simulate-error">{error}</div>}
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

const TONE_TEXT = { ok: "text-[#166534]", warn: "text-[#92400E]", danger: "text-[#991B1B]" };

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
      <p className="text-sm text-[#5F5F5A]">
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
      {error && <div role="alert" className="text-sm text-[#991B1B]" data-testid="smtp-test-error">{error}</div>}
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
  }, []);

  return (
    <div className="p-6 md:p-10 space-y-6 max-w-5xl" data-testid="sending-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="mono-accent">// controlled.sending</div>
          <h1 className="text-4xl font-black tracking-tighter">Sending</h1>
          <p className="text-[#5F5F5A] mt-1 max-w-2xl">Limits, emergency stop and the history of dispatched messages. Dry-run by default; real e-mail leaves over SMTP only when live sending is enabled. A message stuck in “sending” has an unknown outcome: check the mailbox before sending again.</p>
        </div>
        <button className="btn-ghost" onClick={page.reload} data-testid="refresh"><ArrowsClockwise size={14} /> REFRESH</button>
      </div>

      {page.loading && !page.data && <LoadingBlock label="Loading sending status…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}

      {page.data && (
        <>
          <StatusPanel status={page.data.status} settings={page.data.settings} />
          <LimitsForm key={JSON.stringify(page.data.limits)} limits={page.data.limits} canEdit={edit} onSaved={page.reload} />
          {edit && <SmtpTestPanel onDone={page.reload} />}
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
                  <thead className="bg-[#FAFAF7] border-b border-[#D6D3C8]">
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
    </div>
  );
}
