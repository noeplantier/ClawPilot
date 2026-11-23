import { Link } from "react-router-dom";
import { Database, FileArrowUp, MapTrifold } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { LIVE_MS, useMandateLive } from "@/lib/live";
import { importsApi, mapApi, prospectsApi, useAsync } from "@/lib/outreach";
import { mergeHistory } from "@/lib/batchHistory";
import { formatDateTime } from "@/lib/outreachFormat";
import DraftJobsStrip from "@/components/outreach/DraftJobsStrip";
import { EmptyBlock } from "@/components/outreach/States";

const LAUNCH = [
  { to: "/app/map", icon: MapTrifold, title: "Search the map", text: "Draw an area, pick an activity: the places published on OpenStreetMap, then add them." },
  { to: "/app/prospects/import", icon: FileArrowUp, title: "Import a list", text: "A CSV or JSON you may use, with its origin and legal basis recorded." },
  { to: "/app/sources", icon: Database, title: "Run a source", text: "Authorised directories and public sources, one run at a time." },
];
const TONE = { success: "chip-success", danger: "chip-danger", warn: "chip-warn" };

function Metric({ label, value, testId }) {
  return (
    <div className="rounded-lg border border-border px-3 py-2">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="font-display text-xl font-bold" data-testid={testId}>{value}</dd>
    </div>
  );
}

// What was launched and how it is going, from what the server stored. Launching happens on each screen (a search is
// drawn on the map, an import has its form); this page only gathers the progress. Nothing here is simulated.
export default function Batches() {
  const searches = useAsync(() => mapApi.recent(20).catch(() => []), [], { key: "batches:searches", intervalMs: LIVE_MS });
  const imports = useAsync(() => importsApi.list().catch(() => []), [], { key: "batches:imports", intervalMs: LIVE_MS });
  const queue = useAsync(() => prospectsApi.toEnrich({ limit: 1 }).catch(() => null), [], { key: "batches:queue", intervalMs: LIVE_MS });
  const mandates = useAsync(() => api.get("/mandates").then((r) => r.data).catch(() => []), [], { key: "mandates:list", intervalMs: LIVE_MS });
  const mandate = (mandates.data || []).find((m) => m.status === "active") || (mandates.data || [])[0] || null;
  const live = useMandateLive(
    (since, signal) => api.get(`/mandates/${mandate.id}/live`, { params: since ? { since } : {}, signal }).then((r) => r.data),
    mandate?.id,
    { enabled: !!mandate }
  );
  const history = mergeHistory(searches.data, imports.data);
  const counts = live.data?.counts;
  const events = live.data?.events || [];
  const num = (value) => (counts ? value : "—"); // never show a invented zero for a stream we have not read
  return (
    <div className="p-6 md:p-10 space-y-8" data-testid="batches-page">
      <div>
        <div className="mono-accent">// outreach.batches</div>
        <h1 className="text-4xl font-black tracking-tighter">Batches</h1>
        <p className="text-soft mt-1 max-w-2xl">Launch a search or an import, follow what is being prepared, and find what ran before.</p>
      </div>

      <section className="grid gap-3 md:grid-cols-3" aria-label="Launch">
        {LAUNCH.map(({ to, icon: Icon, title, text }) => (
          <Link key={to} to={to} className="surface p-5 space-y-2 hover:border-brand-violet/60 transition-colors" data-testid={`launch-${to.split("/").pop()}`}>
            <Icon size={22} weight="duotone" className="text-brand-lilac" />
            <div className="font-display font-semibold">{title}</div>
            <p className="text-sm text-soft">{text}</p>
          </Link>
        ))}
      </section>

      <section className="surface p-5 space-y-3" aria-label="Mandat" data-testid="mandate-live">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-lg font-bold">Mandat en direct</h2>
          <span className="chip" data-testid="mandate-live-status">
            {live.data?.status || (mandates.loading ? "…" : "aucun mandat")}
          </span>
        </div>
        {!mandate ? (
          <p className="text-sm text-soft">Aucun mandat : créez-en un pour démarrer la découverte automatique.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 text-xs" data-testid="mandate-live-flags">
              <span className="chip">{counts?.discovery_in_progress ? "Découverte en cours" : "Découverte au repos"}</span>
              {live.data?.paused && <span className="chip chip-warn">En pause</span>}
              {live.data?.stopped && <span className="chip chip-danger">Arrêté</span>}
              {live.reconnecting && <span className="chip chip-warn" data-testid="mandate-live-reconnecting">Reconnexion…</span>}
            </div>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="mandate-live-counts">
              <Metric label="Leads découverts" value={num(counts?.leads_discovered)} testId="mandate-live-discovered" />
              <Metric label="Doublons exclus" value={num(counts?.duplicates_excluded)} testId="mandate-live-duplicates" />
              <Metric label="Leads qualifiés" value={num(counts?.leads_qualified)} testId="mandate-live-qualified" />
              <Metric label="Hot Leads" value={num(counts?.hot_leads)} testId="mandate-live-hot" />
            </dl>
            {live.data?.streams?.drafts?.available && (
              <dl className="grid grid-cols-3 md:grid-cols-5 gap-2" data-testid="mandate-live-drafts">
                {["queued", "generating", "ready", "failed", "unavailable"].map((key) => (
                  <Metric key={key} label={key} value={live.data.streams.drafts[key]} testId={`mandate-live-draft-${key}`} />
                ))}
              </dl>
            )}
            {live.data?.streams?.send_queue?.available && (
              <dl className="grid grid-cols-3 md:grid-cols-6 gap-2" data-testid="mandate-live-send-queue">
                {["planned", "processing", "accepted", "failed", "bounced", "reply"].map((key) => (
                  <Metric key={key} label={key} value={live.data.streams.send_queue[key]} testId={`mandate-live-send-${key}`} />
                ))}
              </dl>
            )}
            {(live.data?.streams?.replies || live.data?.streams?.oppositions) && (
              <p className="text-xs text-soft" data-testid="mandate-live-replies">
                Réponses : {live.data.streams.replies?.available ? live.data.streams.replies.count : "—"} ·
                Oppositions : {live.data.streams.oppositions?.available ? live.data.streams.oppositions.count : "—"}
              </p>
            )}
            {live.data?.streams?.reply_collection?.available === false && (
              <p className="text-xs text-faint" data-testid="mandate-live-reply-collection">
                Collecte des réponses non configurée : aucun envoi automatique ne démarrera tant qu’une boîte IMAP n’est pas renseignée.
              </p>
            )}
            {live.data?.streams?.stop_reason && (
              <p className="text-xs text-amber-300" data-testid="mandate-live-stop-reason">
                Arrêt automatique : {live.data.streams.stop_reason}
              </p>
            )}
            {live.data?.latest_batch?.error_summary && (
              <p className="text-xs text-red-300" data-testid="mandate-live-error">{live.data.latest_batch.error_summary}</p>
            )}
            {events.length > 0 && (
              <ul className="text-xs text-soft divide-y divide-border" data-testid="mandate-live-events">
                {events.map((e) => (
                  <li key={e.id} className="py-1 flex gap-2 justify-between">
                    <span>{e.action}</span>
                    <time className="text-faint" dateTime={e.at}>{formatDateTime(e.at)}</time>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <section className="surface p-5 space-y-3" aria-label="Progress" data-testid="batches-progress">
        <h2 className="font-display text-lg font-bold">In progress</h2>
        <DraftJobsStrip />
        <div className="text-xs" data-testid="batches-queue">
          {queue.data ? (
            <>
              <b>To enrich</b> · {queue.data.total} prospect{queue.data.total === 1 ? "" : "s"} wait for an e-mail, a phone, an address or a position.{" "}
              <Link to="/app/prospects/to-enrich" className="underline">Open the queue</Link>
            </>
          ) : "…"}
        </div>
      </section>

      <section className="space-y-3" aria-label="History">
        <h2 className="font-display text-lg font-bold">History</h2>
        {history.length === 0 && !searches.loading && !imports.loading ? (
          <EmptyBlock title="Nothing was launched yet">Run a search on the map or import a list: it will be listed here with its result.</EmptyBlock>
        ) : (
          <div className="surface divide-y divide-border" data-testid="batches-history">
            {history.map((e) => (
              <Link key={e.key} to={e.to} className="flex flex-wrap items-center gap-3 p-4 hover:bg-white/[0.03]" data-testid="batches-row">
                <span className="mono-accent w-28 shrink-0">{e.kind}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{e.title}</span>
                <span className="text-sm text-soft">{e.detail}</span>
                <span className={`chip ${TONE[e.tone]}`}>{e.status}</span>
                <time className="text-xs text-faint w-36 text-right" dateTime={e.at || undefined}>{e.at ? formatDateTime(e.at) : "—"}</time>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
