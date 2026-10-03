import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, ChatCircleDots, Pause, Play, ShieldCheck } from "@phosphor-icons/react";
import { DASH, ago, kpiCards, modeOf, pct, quotaShare, seriesHasData, seriesSummary, shortDay } from "@/lib/dashboardFormat";
import { EmptyBlock } from "@/components/outreach/States";

export function Widget({ title, kicker, testId, action, children }) {
  return (
    <section className="surface p-5 space-y-3" data-testid={testId} aria-label={title}>
      <header className="flex items-start justify-between gap-3">
        <div>
          {kicker && <div className="mono-accent">{kicker}</div>}
          <h2 className="font-display text-lg font-bold tracking-tight">{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function KpiStrip({ kpis, limits }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3" data-testid="kpi-strip">
      {kpiCards(kpis, limits).map((c, i) => (
        <motion.div
          key={c.key}
          className={`pos-kpi pos-kpi-${c.accent}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, duration: 0.3 }}
          data-testid={`kpi-${c.key}`}
        >
          <div className="pos-kpi-body">
            <div className="mono-accent !text-white/60">{c.label}</div>
            <div className="font-display text-3xl font-black tracking-tight mt-1" data-testid={`kpi-${c.key}-value`}>{c.value}</div>
            <div className="text-xs text-white/60 mt-1" data-testid={`kpi-${c.key}-hint`}>{c.hint}</div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

export function ActivityChart({ series }) {
  if (!seriesHasData(series)) {
    return (
      <EmptyBlock title="No message sent in the last 14 days" testId="chart-empty">
        <p>Dispatch an approved draft and it appears here, with the replies it receives.</p>
      </EmptyBlock>
    );
  }
  const data = series.map((p) => ({ ...p, day: shortDay(p.date) }));
  return (
    <div role="img" aria-label={seriesSummary(series)} data-testid="activity-chart" className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="posSent" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563EB" stopOpacity={0.5} /><stop offset="100%" stopColor="#2563EB" stopOpacity={0} /></linearGradient>
            <linearGradient id="posReplied" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7C3AED" stopOpacity={0.5} /><stop offset="100%" stopColor="#7C3AED" stopOpacity={0} /></linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E2D6" />
          <XAxis dataKey="day" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Area type="monotone" dataKey="sent" name="sent" stroke="#2563EB" fill="url(#posSent)" strokeWidth={2} />
          <Area type="monotone" dataKey="replied" name="replies" stroke="#7C3AED" fill="url(#posReplied)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LiveSignals({ prospects, signals }) {
  if (prospects.length === 0 && signals.length === 0) {
    return (
      <EmptyBlock title="No prospect discovered yet" testId="signals-empty">
        <p>Run a discovery or import a list: new prospects and the signals detected on them show up here.</p>
        <Link to="/app/prospects" className="btn-ink inline-flex">GO TO PROSPECTS</Link>
      </EmptyBlock>
    );
  }
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <ul className="space-y-2" data-testid="latest-prospects">
        {prospects.map((p) => (
          <li key={p.id}>
            <Link to={`/app/prospects/${p.id}`} className="flex items-center justify-between gap-2 text-sm hover:underline">
              <span className="truncate">{p.name}{p.city ? <span className="text-[#5F5F5A]"> · {p.city}</span> : null}</span>
              <span className="chip chip-ink shrink-0">{p.score === null ? "not scored" : p.score}</span>
            </Link>
          </li>
        ))}
      </ul>
      <ul className="space-y-2" data-testid="latest-signals">
        {signals.map((s, i) => (
          <li key={`${s.lead_id}-${s.key}-${i}`} className="pos-signal-chip" style={{ animationDelay: `${i * 40}ms` }}>
            <span className="chip chip-warn">{s.label}</span>
            <div className="text-xs text-[#595955] mt-1"><Link to={`/app/prospects/${s.lead_id}`} className="font-semibold hover:underline">{s.name}</Link> — {s.evidence}</div>
          </li>
        ))}
        {signals.length === 0 && <li className="text-sm text-[#5F5F5A]" data-testid="signals-none">No signal detected yet (an unknown signal is not a finding).</li>}
      </ul>
    </div>
  );
}

export function CampaignHealth({ campaigns }) {
  if (campaigns.length === 0) {
    return (
      <EmptyBlock title="No campaign yet" testId="campaigns-empty">
        <p>Create a campaign to follow its sends, open and reply rates.</p>
        <Link to="/app/campaigns" className="btn-ink inline-flex">GO TO CAMPAIGNS</Link>
      </EmptyBlock>
    );
  }
  return (
    <table className="w-full text-sm" data-testid="campaign-health">
      <thead><tr className="text-left mono-accent"><th className="py-1">campaign</th><th>sent</th><th>open</th><th>reply</th></tr></thead>
      <tbody>
        {campaigns.map((c) => (
          <tr key={c.id} className="border-t border-[#EEE]" data-testid="campaign-row">
            <td className="py-1.5 pr-2"><span className="font-medium">{c.name}</span> <span className="chip chip-ink ml-1">{c.status}</span></td>
            <td>{c.sent}</td>
            <td data-testid="campaign-open-rate">{pct(c.open_rate)}</td>
            <td data-testid="campaign-reply-rate">{pct(c.reply_rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LimitsCompliance({ limits, canEdit, busy, onTogglePause }) {
  const mode = modeOf(limits);
  const share = quotaShare(limits);
  return (
    <div className="space-y-3" data-testid="limits-widget">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`chip chip-${mode.tone}`} data-testid="limits-mode">{mode.label}</span>
        {limits.blocked_by && !limits.kill_switch && !limits.paused && <span className="chip chip-warn" data-testid="limits-blocked">blocked: {limits.blocked_by}</span>}
      </div>
      <div>
        <div className="flex justify-between text-xs text-[#595955]"><span>Today</span><span data-testid="limits-quota">{limits.sent_today} / {limits.max_per_day}</span></div>
        <div className="h-2 rounded-full bg-[#E5E2D6] overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={limits.max_per_day} aria-valuenow={limits.sent_today} aria-label="Daily send quota">
          <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: share >= 1 ? "#DC2626" : "linear-gradient(90deg,#2563EB,#7C3AED)" }} />
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-[#5F5F5A]">last hour</dt><dd data-testid="limits-hour">{limits.sent_last_hour} / {limits.max_per_hour}</dd>
        <dt className="text-[#5F5F5A]">min delay</dt><dd>{limits.min_delay_seconds}s</dd>
        <dt className="text-[#5F5F5A]">kill switch</dt><dd data-testid="limits-kill">{limits.kill_switch ? "ON" : "off"}</dd>
        <dt className="text-[#5F5F5A]">organisation</dt><dd data-testid="limits-paused">{limits.paused ? "paused" : "active"}</dd>
        <dt className="text-[#5F5F5A]">sandbox allowlist</dt><dd>{limits.sandbox ? `${limits.allowlist_size} address(es)` : "sandbox off"}</dd>
        <dt className="text-[#5F5F5A]">SMTP</dt><dd>{limits.smtp_configured ? "configured" : "not configured"}</dd>
      </dl>
      <div className="flex gap-2 flex-wrap">
        {canEdit && (
          <button className="btn-ghost" disabled={busy} onClick={onTogglePause} data-testid="limits-toggle-pause">
            {limits.paused ? <><Play size={14} /> RESUME SENDING</> : <><Pause size={14} /> PAUSE SENDING</>}
          </button>
        )}
        <Link to="/app/sending" className="btn-ghost" data-testid="limits-open-sending"><ShieldCheck size={14} /> LIMITS &amp; TEST</Link>
      </div>
    </div>
  );
}

export function Inbox({ items }) {
  if (items.length === 0) {
    return (
      <EmptyBlock title="No reply yet" testId="inbox-empty">
        <p>Replies appear here. Real replies and bounces are not read from your mailbox yet: record them by hand if needed.</p>
      </EmptyBlock>
    );
  }
  return (
    <ul className="space-y-3" data-testid="inbox-list">
      {items.map((m) => (
        <li key={m.message_id} className="text-sm" data-testid="inbox-item">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium inline-flex items-center gap-1"><ChatCircleDots size={14} /> {m.name}</span>
            <span className="text-xs text-[#5F5F5A]">{ago(m.at)}{m.simulated ? " · simulated" : ""}</span>
          </div>
          <p className="text-[#595955] mt-0.5">{m.excerpt || DASH}</p>
          <Link to={`/app/prospects/${m.lead_id}`} className="text-xs font-semibold inline-flex items-center gap-1 mt-1 hover:underline" data-testid="inbox-follow-up">
            OPEN PROSPECT TO FOLLOW UP <ArrowRight size={12} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
