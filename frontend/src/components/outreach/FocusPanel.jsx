import { Link } from "react-router-dom";
import { Compass, Fire, MapPin, Target } from "@phosphor-icons/react";
import { focusApi } from "@/lib/outreach";
import { LIVE_MS, useLive } from "@/lib/live";
import { EMPTY_FOCUS, leadLine, leadLink, mapLink, zoneLine } from "@/lib/focus";

// Next best moves, recomputed from your own leads every few seconds: the towns holding the most hot leads that can be called and
// e-mailed, and the hottest of those leads, website first. Nothing is estimated: with nothing qualifying, the lists stay empty.
export default function FocusPanel() {
  const live = useLive(() => focusApi.get(), [], { itemsOf: (d) => d.leads, key: "suggestions:focus" });
  const d = live.data;
  const empty = d && d.zones.length === 0 && d.leads.length === 0;
  return (
    <section className="surface p-5 space-y-4" data-testid="focus-panel" aria-label="Where to prospect next">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="mono-accent inline-flex items-center gap-2"><Compass size={14} weight="fill" /> // live.focus</div>
          <h2 className="font-display text-xl font-bold">Where to prospect next</h2>
          <p className="text-xs text-muted-foreground">Hot leads with a phone and an e-mail, website first. <Link to="/app/campaigns" className="underline">Suggested campaigns</Link></p>
        </div>
        <p className="text-xs inline-flex items-center gap-2" role="status" aria-live="polite" data-testid="focus-live">
          <span className="pos-live-dot" aria-hidden="true" />
          {live.stale ? "Refresh failed: showing the last data. " : ""}
          {live.updatedAt ? `Live · updated ${live.updatedAt.toLocaleTimeString()} · every ${LIVE_MS / 1000} s` : "Loading…"}
        </p>
      </div>
      {live.error && <div role="alert" className="text-sm text-red-300" data-testid="focus-error">{live.error}</div>}
      {empty && <p className="text-sm text-muted-foreground" data-testid="focus-empty">{EMPTY_FOCUS}</p>}
      {d && !empty && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div>
            <h3 className="mono-accent mb-2">zones</h3>
            {d.zones.length === 0 && <p className="text-sm text-muted-foreground">No town holds a hot lead with a phone and an e-mail yet.</p>}
            <ul className="space-y-2">
              {d.zones.map((z) => (
                <li key={z.key}>
                  <Link to={mapLink(z)} className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-violet" data-testid="focus-zone">
                    <MapPin size={18} weight="duotone" aria-hidden="true" />
                    <span className="min-w-0 flex-1"><strong className="block truncate">{z.city}</strong><span className="block text-xs text-muted-foreground">{zoneLine(z)}</span></span>
                    <span className="text-xs underline shrink-0">OPEN ON THE MAP</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mono-accent mb-2">contact first</h3>
            {d.leads.length === 0 && <p className="text-sm text-muted-foreground">No hot lead can be contacted by phone and e-mail yet.</p>}
            <ul className="space-y-2">
              {d.leads.map((l) => (
                <li key={l.id}>
                  <Link to={leadLink(l)} className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-violet" data-testid="focus-lead">
                    <Target size={18} weight="duotone" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <strong className="block truncate">{l.name}</strong>
                      <span className="block text-xs text-muted-foreground truncate">{leadLine(l)}</span>
                      <span className="block font-mono text-xs truncate">{l.phone} · {l.email}{l.website ? ` · ${l.website.replace(/^https?:\/\//i, "")}` : ""}</span>
                    </span>
                    <span className="chip chip-hot shrink-0"><Fire size={12} weight="fill" aria-hidden="true" /> {l.heat.value}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
