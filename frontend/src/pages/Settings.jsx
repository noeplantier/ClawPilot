import { useState } from "react";
import { toast } from "sonner";
import {
  ArrowsClockwise, Buildings, Copy, Database, EnvelopeOpen, Envelope, IdentificationCard, Link as LinkIcon, MapPin, MapTrifold,
  PaperPlaneTilt, Play, Plugs, Shield, ShieldCheck, Sparkle, Warning, WhatsappLogo,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useLive } from "@/lib/live";
import { describeApiError } from "@/lib/outreachFormat";
import { TONE, effective, groupItems, needsList, summarize, testGeocoder, testable } from "@/lib/integrations";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";

// Every status on this page is computed by the server from its real configuration (GET /settings/integrations), refreshed every
// 30 s while the tab is visible. A "Test" only refines it for this session. Secrets are never typed, shown or stored here: the
// page names the variables to set in the hosting dashboard.

const SETTINGS_LIVE_MS = 30000;
const ICONS = {
  database: Database, public_url: LinkIcon, osm: MapTrifold, geocoder: MapPin, registry: Buildings, sender: IdentificationCard,
  sending_mode: PaperPlaneTilt, smtp: Envelope, imap: EnvelopeOpen, sendgrid: Envelope, twilio: WhatsappLogo,
  twilio_webhook: ShieldCheck, sendgrid_webhook: ShieldCheck, ai: Sparkle,
};

export default function Settings() {
  const { user, org } = useAuth();
  const live = useLive(() => api.get("/settings/integrations").then((r) => r.data), [], { intervalMs: SETTINGS_LIVE_MS, itemsOf: (d) => d.items });
  const s = live.data;
  const canTest = user?.role === "owner" || user?.role === "admin";

  return (
    <div className="p-6 md:p-10 max-w-6xl space-y-8" data-testid="settings-page">
      <div>
        <div className="mono-accent">// control.panel</div>
        <h1 className="text-4xl font-black tracking-tighter">Settings</h1>
        <p className="text-[#5F5F5A] mt-1">Organization profile and the live status of every integration of this server.</p>
      </div>

      <section className="surface p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Shield size={18} className="text-[#4F46E5]" />
          <h2 className="font-display text-xl font-bold">Profile</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <Row label="operator.name" value={user?.full_name} />
          <Row label="email" value={user?.email} mono />
          <Row label="role" value={user?.role} mono />
          <Row label="organization" value={org?.name} />
          <Row label="plan" value={org?.plan} mono />
          <Row label="org.id" value={org?.id} mono truncate />
        </div>
      </section>

      <section className="space-y-5" data-testid="integrations">
        <div className="flex items-center gap-2">
          <Plugs size={18} className="text-[#4F46E5]" />
          <h2 className="font-display text-xl font-bold">Integrations</h2>
        </div>
        {live.loading && !s && <LoadingBlock label="Reading the server configuration…" />}
        {live.error && <ErrorBlock message={live.error} onRetry={live.reload} />}
        {s && <Integrations s={s} live={live} canTest={canTest} />}
      </section>
    </div>
  );
}

function Integrations({ s, live, canTest }) {
  const [results, setResults] = useState({});
  const [running, setRunning] = useState(() => new Set());
  const items = s.items || [];
  const sum = summarize(items, results);

  const mark = (id, on) => setRunning((prev) => { const next = new Set(prev); if (on) next.add(id); else next.delete(id); return next; });

  const run = async (item) => {
    mark(item.id, true);
    try {
      const out = item.test === "browser"
        ? await testGeocoder()
        : (await api.post(`/settings/integrations/${item.id}/test`)).data;
      setResults((prev) => ({ ...prev, [item.id]: { ...out, at: new Date() } }));
    } catch (e) {
      setResults((prev) => ({ ...prev, [item.id]: { ok: false, outcome: "error", detail: describeApiError(e), at: new Date() } }));
    } finally {
      mark(item.id, false);
    }
  };

  // Only what is configured: an unconfigured service would answer "skipped" and spend the rate limit (10 tests a minute).
  const runAll = async () => {
    for (const item of testable(items).filter((i) => ["unchecked", "ready", "partial"].includes(i.status))) {
      if (item.test === "server" && !canTest) continue;
      await run(item);
    }
  };

  return (
    <>
      <div className="surface p-4 flex flex-wrap items-center gap-3" data-testid="int-summary">
        <Chip tone="ready" testId="sum-ready">{sum.ready} READY</Chip>
        <Chip tone="unchecked" testId="sum-unchecked">{sum.unchecked} NOT TESTED</Chip>
        <Chip tone={sum.attention ? "missing" : "off"} testId="sum-attention">{sum.attention} NEED ATTENTION</Chip>
        <Chip tone="off" testId="sum-off">{sum.off} OFF</Chip>
        <span className="text-xs inline-flex items-center gap-2 text-[#4338CA] ml-auto" role="status" aria-live="polite" data-testid="int-live">
          <span className="pos-live-dot" aria-hidden="true" />
          {live.stale ? "Refresh failed: showing the last data. " : ""}
          {live.updatedAt ? `Live · updated ${live.updatedAt.toLocaleTimeString()} · every ${SETTINGS_LIVE_MS / 1000} s` : "Loading…"}
        </span>
        <button onClick={live.reload} className="btn-ghost" data-testid="int-refresh"><ArrowsClockwise size={14} /> REFRESH</button>
        <button onClick={runAll} disabled={running.size > 0} className="btn-primary" data-testid="int-run-all"><Play size={14} weight="fill" /> RUN CHECKS</button>
      </div>

      <p className="text-sm text-[#5F5F5A] flex gap-2" data-testid="int-secrets-note">
        <ShieldCheck size={16} className="shrink-0 mt-0.5 text-[#4F46E5]" />
        <span>
          Keys and passwords are never typed or shown here. Add the variable names listed under an integration in your hosting dashboard
          (Render → your API service → Environment), then redeploy; this page re-reads the server and updates by itself.
        </span>
      </p>

      {groupItems(items).map(([key, label, list]) => (
        <div key={key} className="space-y-3" data-testid={`group-${key}`}>
          <div className="mono-accent">// {label.toLowerCase()}</div>
          <div className="grid lg:grid-cols-2 gap-4">
            {[...list].sort((a, b) => TONE[effective(a, results[a.id]).status].rank - TONE[effective(b, results[b.id]).status].rank).map((item) => (
              <Card key={item.id} item={item} result={results[item.id]} busy={running.has(item.id)} canTest={canTest} onTest={() => run(item)} />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

function Chip({ tone, children, testId }) {
  return <span className={`chip ${TONE[tone].chip}`} data-testid={testId}>{children}</span>;
}

function copyNames(item) {
  try {
    navigator.clipboard.writeText(needsList(item)).then(() => toast.success("Variable names copied"), () => toast.error("Copy is blocked by the browser"));
  } catch {
    toast.error("Copy is blocked by the browser");
  }
}

function Card({ item, result, busy, canTest, onTest }) {
  const Icon = ICONS[item.id] || Plugs;
  const shown = effective(item, result);
  const server = item.test === "server";
  const disabled = busy || (server && !canTest);
  return (
    <div className="surface p-5 space-y-3" data-testid={`int-${item.id}`} data-status={shown.status}>
      <div className="flex items-start gap-3">
        <Icon size={24} weight="duotone" className="text-[#4F46E5] mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-display font-semibold">{item.name}</h3>
            <Chip tone={shown.status} testId={`int-${item.id}-status`}>{shown.label}</Chip>
          </div>
          <p className="text-sm text-[#5F5F5A] mt-1">{item.summary}</p>
        </div>
      </div>

      {item.facts.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono" data-testid={`int-${item.id}-facts`}>
          {item.facts.map(([k, v]) => (
            <div key={k} className="flex gap-2 min-w-0"><span className="text-[#6B7690]">{k}:</span><span className="truncate" title={v}>{v}</span></div>
          ))}
        </div>
      )}

      {item.needs.length > 0 && (
        <div className="rounded-md border border-[#F59E0B]/40 bg-[#FFFBEB] p-3 text-xs space-y-2" data-testid={`int-${item.id}-needs`}>
          <div className="font-semibold text-[#92400E] flex items-center gap-2"><Warning size={14} /> Set in your hosting environment:</div>
          <div className="flex flex-wrap gap-1.5">
            {item.needs.map((n) => <code key={n} className="px-1.5 py-0.5 rounded bg-white border border-[#F59E0B]/40 font-mono">{n}</code>)}
          </div>
          <button onClick={() => copyNames(item)} className="inline-flex items-center gap-1 text-[#92400E] underline" data-testid={`int-${item.id}-copy`}>
            <Copy size={12} /> copy the names
          </button>
        </div>
      )}

      {item.hint && <p className="text-xs text-[#6B7690]" data-testid={`int-${item.id}-hint`}>{item.hint}</p>}

      <div className="flex items-center gap-3 flex-wrap">
        {item.test && (
          <button onClick={onTest} disabled={disabled} className="btn-ghost" data-testid={`int-${item.id}-test`}
            title={server && !canTest ? "Only an owner or an admin can run server checks" : undefined}>
            <Play size={12} weight="fill" /> {busy ? "TESTING…" : item.test === "browser" ? "TEST FROM THIS BROWSER" : "TEST NOW"}
          </button>
        )}
        <span className="mono-accent">{item.docs}</span>
      </div>

      {result && (
        <p className={`text-xs ${result.outcome === "passed" ? "text-[#065F46]" : result.outcome === "skipped" ? "text-[#6B7690]" : "text-[#991B1B]"}`}
          role="status" data-testid={`int-${item.id}-result`}>
          {result.outcome === "passed" ? "✔ " : result.outcome === "skipped" ? "– " : "✖ "}
          {result.detail} <span className="text-[#6B7690]">({result.at.toLocaleTimeString()})</span>
        </p>
      )}
    </div>
  );
}

function Row({ label, value, mono, truncate }) {
  return (
    <div>
      <div className="mono-accent">{label}</div>
      <div className={`mt-1 ${mono ? "font-mono text-sm" : "font-display font-semibold"} ${truncate ? "truncate" : ""}`}>
        {value || "—"}
      </div>
    </div>
  );
}
