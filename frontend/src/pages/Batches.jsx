import { Link } from "react-router-dom";
import { Database, FileArrowUp, MapTrifold } from "@phosphor-icons/react";
import { LIVE_MS } from "@/lib/live";
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

// What was launched and how it is going, from what the server stored. Launching happens on each screen (a search is
// drawn on the map, an import has its form); this page only gathers the progress. Nothing here is simulated.
export default function Batches() {
  const searches = useAsync(() => mapApi.recent(20).catch(() => []), [], { key: "batches:searches", intervalMs: LIVE_MS });
  const imports = useAsync(() => importsApi.list().catch(() => []), [], { key: "batches:imports", intervalMs: LIVE_MS });
  const queue = useAsync(() => prospectsApi.toEnrich({ limit: 1 }).catch(() => null), [], { key: "batches:queue", intervalMs: LIVE_MS });
  const history = mergeHistory(searches.data, imports.data);
  return (
    <div className="p-6 md:p-10 space-y-8" data-testid="batches-page">
      <div>
        <div className="eyebrow">outreach.batches</div>
        <h1 className="mt-3 text-4xl font-bold tracking-tight leading-[1.15]">Batches</h1>
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
